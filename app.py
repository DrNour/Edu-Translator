# EduTranslator Plus (v3)
# English ↔ Arabic translation tutor with pedagogical + classroom management features
# -------------------------------------------------------------------------------
# New in v3 (on top of v2):
# - Password/time-window access control (via secrets)
# - Assignments system (instructor creates code; students translate/post-edit, submit)
# - Student self-translation + post-edit workflow
# - Error identification + targeted exercise generator per submission
# - Exports include assignments and submissions

import os
import re
import io
import zipfile
import uuid
from datetime import datetime, time as _time
from typing import Dict, Any, List

import streamlit as st
import pandas as pd

# Optional dependency for .docx upload
try:
    import docx  # python-docx
except Exception:  # pragma: no cover
    docx = None

from openai import OpenAI

# ------------- App Config -------------
st.set_page_config(page_title="EduTranslator Plus", page_icon="🗣️", layout="wide")

# ------------- Secrets & API -------------
api_key = None
try:
    api_key = st.secrets.get("openai", {}).get("api_key")
except Exception:
    pass
api_key = api_key or os.getenv("OPENAI_API_KEY")
if not api_key:
    st.error(
        "OpenAI API key not found. Add it to `.streamlit/secrets.toml` under [openai] api_key, or set OPENAI_API_KEY.")
    st.stop()

client = OpenAI(api_key=api_key)
MODEL = "gpt-4o-mini"  # switch to "gpt-4o" for higher quality

# ------------- Simple Access Control (password + time window) -------------
# Configure in .streamlit/secrets.toml (recommended):
# [app]
# password = "change-me"
# open_start = "00:00"  # 24h HH:MM (server local time)
# open_end   = "23:59"
app_cfg = {}
try:
    app_cfg = st.secrets.get("app", {})
except Exception:
    app_cfg = {}
REQUIRED_PASSWORD = app_cfg.get("password")
OPEN_START = app_cfg.get("open_start", "00:00")
OPEN_END = app_cfg.get("open_end", "23:59")

def _in_window(open_start: str, open_end: str) -> bool:
    try:
        sh, sm = map(int, open_start.split(":"))
        eh, em = map(int, open_end.split(":"))
        now = datetime.now().time()
        return _time(sh, sm) <= now <= _time(eh, em)
    except Exception:
        return True

if not _in_window(OPEN_START, OPEN_END):
    st.error(f"App is closed right now. Open hours: {OPEN_START}–{OPEN_END}.")
    st.stop()

if REQUIRED_PASSWORD:
    if not st.session_state.get("_authed"):
        with st.sidebar:
            st.warning("This app is restricted. Enter the class password to continue.")
            pwd = st.text_input("Class password", type="password")
            if st.button("Unlock"):
                if pwd == REQUIRED_PASSWORD:
                    st.session_state._authed = True
                    st.success("Unlocked for this session.")
                else:
                    st.error("Wrong password.")
        if not st.session_state.get("_authed"):
            st.stop()

# ------------- Utilities -------------
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

ARABIC_RE = re.compile(r"[\u0600-\u06FF]")

def is_arabic_text(text: str) -> bool:
    return bool(ARABIC_RE.search(text or ""))

@st.cache_data(show_spinner=False)
def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# Safe LLM call with fallback

def llm(messages: List[Dict[str, str]], temperature: float = 0.3) -> str:
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=temperature,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"⚠️ LLM call failed: {e}"

# Logging helpers

def get_session_id() -> str:
    if "session_id" not in st.session_state:
        st.session_state.session_id = str(uuid.uuid4())[:8]
    return st.session_state.session_id


def append_log(csv_path: str, row: Dict[str, Any]):
    df = pd.DataFrame([row])
    if os.path.exists(csv_path):
        df_existing = pd.read_csv(csv_path)
        df = pd.concat([df_existing, df], ignore_index=True)
    df.to_csv(csv_path, index=False)

# ------------- Sidebar (identity + settings) -------------
with st.sidebar:
    st.header("Settings")

    # ---- Role & permissions (optional) ----
    roles_cfg = {}
    try:
        roles_cfg = st.secrets.get("roles", {})
    except Exception:
        roles_cfg = {}
    INSTR_PWD = roles_cfg.get("instructor_password")

    if "role" not in st.session_state:
        st.session_state.role = "Student"
    role = st.selectbox("Role", ["Student", "Instructor"], index=0 if st.session_state.role == "Student" else 1)
    st.session_state.role = role

    instructor_unlocked = (role == "Instructor")
    if role == "Instructor" and INSTR_PWD:
        ipwd = st.text_input("Instructor password", type="password")
        if ipwd != INSTR_PWD:
            st.warning("Enter the instructor password to unlock instructor tools.")
            instructor_unlocked = False
        else:
            st.success("Instructor tools unlocked.")
    # Lightweight identity for class analytics
    student_name = st.text_input("Your name / initials (optional)")
    group_code = st.text_input("Class/Group code (e.g., ENG201-1)")
    session_id = get_session_id()
    st.caption(f"Session ID: {session_id}")

    st.markdown("—")

    auto_detect = st.checkbox("Auto-detect source language", value=True)

    src = st.selectbox("Source language", ["Arabic", "English"], index=0)
    tgt = st.selectbox("Target language", ["English", "Arabic"], index=1)

    if auto_detect:
        st.caption("Auto-detect uses Arabic script to decide source/target.")

    cefr = st.select_slider("CEFR level", options=["A2", "B1", "B2", "C1"], value="B1")
    style = st.selectbox("Explanation style", ["Concise", "Teacherly", "Exam-focused"])

    tone = st.selectbox("Target tone (natural translation)", [
        "Neutral", "Academic", "Informal", "Professional", "Literary"
    ])
    domain = st.selectbox("Terminology domain (optional)", [
        "General", "Engineering", "Legal", "Media", "Medical", "Business"
    ])

    st.markdown(
        "<small>Note: This tool is a learning aid. Aim to understand and justify your choices.</small>", unsafe_allow_html=True
    )

# ------------- Tabs -------------
tabs = st.tabs([
    "Translate", "Explain", "Collocations / Idioms", "Quick Quiz", "Mini Challenges", "Assignments", "Teacher Dashboard", "Export"
])

# ------------- Translate Tab -------------
with tabs[0]:
    st.subheader("Translate: Literal vs. Natural")

    uploaded = st.file_uploader("Optional: upload a .txt or .docx to prefill text", type=["txt", "docx"], accept_multiple_files=False)
    prefill_text = ""
    if uploaded is not None:
        if uploaded.type == "text/plain":
            prefill_text = uploaded.read().decode("utf-8", errors="ignore")
        elif uploaded.name.lower().endswith(".docx"):
            if docx is None:
                st.warning("python-docx not installed; cannot read .docx. Install with `pip install python-docx`.")
            else:
                d = docx.Document(uploaded)
                prefill_text = "\n".join([p.text for p in d.paragraphs])

    text = st.text_area("Paste a sentence or short paragraph", value=prefill_text, height=160)

    # Auto-detect src/tgt
    if auto_detect and text.strip():
        if is_arabic_text(text):
            src_auto, tgt_auto = "Arabic", "English"
        else:
            src_auto, tgt_auto = "English", "Arabic"
        st.caption(f"Auto-detected → Source: {src_auto} | Target: {tgt_auto}")
    else:
        src_auto, tgt_auto = src, tgt

    colA, colB, colC = st.columns([1,1,1])
    with colA:
        run_btn = st.button("Translate")
    with colB:
        back_btn = st.button("Back-translation check")
    with colC:
        st.write("")

    def translate_core(source_text: str) -> Dict[str, str]:
        system = "You are a bilingual English–Arabic translation tutor. Provide helpful, concise explanations."
        prompt = f"""
        Source language: {src_auto}. Target language: {tgt_auto}.
        Domain/context: {domain}.

        Text:
        {source_text}

        Tasks:
        1) Provide two translations:
           (a) Literal (close to source syntax),
           (b) Natural/idiomatic (tone: {tone}).
        2) List 3–5 key choices (word sense, grammar, culture, collocations).
        3) Contrastive hints for Arabic↔English learners (likely pitfalls).
        Format with clear headings and bullets.
        """
        out = llm([
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ])
        return {"analysis": out}

    def detect_errors(source_text: str, literal: str, natural: str) -> str:
        system = "You are a translation QA coach."
        prompt = f"""
        Label the main error TYPES visible when comparing translations.
        Categories to use: LEXICAL CHOICE, GRAMMAR/SYNTAX, IDIOMATICITY, COLLOCATION, STYLE/REGISTER, PUNCTUATION.
        Input source: {source_text}
        Literal translation: {literal}
        Natural translation: {natural}
        Output: bullet list with category labels (ALL-CAPS) and one-sentence justification each.
        """
        return llm([
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ])

    if run_btn and text.strip():
        result = translate_core(text)
        st.markdown(result["analysis"])  # includes literal/natural sections + hints

        # Heuristic extraction (best-effort)
        literal_guess, natural_guess = "", ""
        try:
            parts = re.split(r"(?im)^\s*(?:\(a\)\s*Literal|Literal)\s*[:\-]?|^\s*(?:\(b\)\s*Natural|Natural.*?)\s*[:\-]?", result["analysis"])  # heuristic
            if len(parts) >= 3:
                literal_guess = parts[1].strip()[:800]
                natural_guess = parts[2].strip()[:800]
        except Exception:
            pass

        if literal_guess or natural_guess:
            with st.expander("Error-type detection (auto)"):
                report = detect_errors(text, literal_guess, natural_guess)
                st.markdown(report)

        # Reflection box
        st.markdown("---")
        st.subheader("🔎 Reflection (learning log)")
        reflection = st.text_area(
            "Which version sounds more natural for this context and why? Mention 2–3 reasons.", height=120
        )
        if st.button("Save reflection"):
            row = {
                "timestamp": now_str(),
                "student": student_name or "",
                "group": group_code or "",
                "session": session_id,
                "source_lang": src_auto,
                "target_lang": tgt_auto,
                "domain": domain,
                "tone": tone,
                "text": text,
                "reflection": reflection,
            }
            append_log(os.path.join(LOG_DIR, "reflections.csv"), row)
            st.success("Reflection saved (logs/reflections.csv)")

        # Save translation event
        append_log(os.path.join(LOG_DIR, "translations.csv"), {
            "timestamp": now_str(),
            "student": student_name or "",
            "group": group_code or "",
            "session": session_id,
            "source_lang": src_auto,
            "target_lang": tgt_auto,
            "domain": domain,
            "tone": tone,
            "text": text[:4000],
        })

    if back_btn and text.strip():
        # Natural translation, then back-translate it
        natural_out = llm([
            {"role": "system", "content": "You are a bilingual translator."},
            {"role": "user", "content": f"Translate from {src_auto} to {tgt_auto}. Tone: {tone}. Domain: {domain}. Text: {text}"},
        ])
        st.markdown("**Natural translation:**\n\n" + natural_out)
        back_out = llm([
            {"role": "system", "content": "You are a careful back-translator."},
            {"role": "user", "content": f"Back-translate this {tgt_auto} text into {src_auto}, preserving meaning rather than word order: {natural_out}"},
        ])
        st.markdown("**Back-translation:**\n\n" + back_out)

# ------------- Explain Tab -------------
with tabs[1]:
    st.subheader("Explain a word or phrase (CEFR-aware)")
    lemma = st.text_input("Word/phrase (e.g., albeit, run into, catalyst)")
    if st.button("Explain") and lemma.strip():
        system = "You are a bilingual English–Arabic tutor."
        prompt = f"""
        Explain '{lemma}' for a {cefr} learner. Style: {style}.
        Output language: {tgt}.
        Include:
        - Part of speech & short CEFR-friendly definition.
        - 2 example sentences with brief glosses.
        - Register notes (formal/informal; academic/spoken).
        - Common patterns & collocations (verb+object, adj+noun, prepositions).
        - Typical pitfalls for {src} speakers (contrastive notes).
        Keep it compact and scannable.
        """
        out = llm([
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ])
        st.markdown(out)

        if st.button("➕ Save to My Glossary"):
            row = {
                "timestamp": now_str(),
                "student": student_name or "",
                "group": group_code or "",
                "session": session_id,
                "lemma": lemma,
                "notes": out,
            }
            append_log(os.path.join(LOG_DIR, "glossary.csv"), row)
            st.success("Saved to glossary (logs/glossary.csv)")

# ------------- Collocations / Idioms Tab -------------
with tabs[2]:
    st.subheader("Collocations / Idioms")
    key = st.text_input("Headword or idiom (e.g., heavy, commit, break the ice)")
    mode = st.radio("Type", ["Collocations", "Idiom / Fixed expression"], horizontal=True)
    if st.button("Generate") and key.strip():
        if mode == "Collocations":
            prompt = f"""
            List the 6 most useful collocations for '{key}' in {tgt}.
            Mix patterns (adj+noun, verb+noun, noun+prep, verb+prep). For each: one example.
            Add 3 brief 'watch-outs' for {src} learners (false friends, word order, prepositions).
            """
        else:
            prompt = f"""
            Explain the idiom/fixed expression '{key}' in {tgt} for a {cefr} learner.
            Give: meaning, usage conditions, 1 example, one near-synonym and the difference,
            and any register/cultural notes. Add a short memory tip.
            """
        out = llm([
            {"role": "system", "content": "You are a helpful collocation/idiom tutor."},
            {"role": "user", "content": prompt},
        ])
        st.markdown(out)

        if st.button("➕ Save to My Glossary", key="save_col"):
            row = {
                "timestamp": now_str(),
                "student": student_name or "",
                "group": group_code or "",
                "session": session_id,
                "lemma": key + (" (idiom)" if mode != "Collocations" else ""),
                "notes": out,
            }
            append_log(os.path.join(LOG_DIR, "glossary.csv"), row)
            st.success("Saved to glossary (logs/glossary.csv)")

# ------------- Quick Quiz Tab (gamified) -------------
with tabs[3]:
    st.subheader("Quick Quiz (formative practice)")
    target = st.text_input("Target word/collocation/idiom (e.g., take into account)")
    if "quiz_items" not in st.session_state:
        st.session_state.quiz_items = []
        st.session_state.quiz_score = 0
        st.session_state.quiz_total = 0

    if st.button("Create quiz") and target.strip():
        prompt = f"""
        Create a 6-item micro-quiz about '{target}' in {tgt} for {cefr} learners.
        Format STRICTLY in JSON with this schema:
        {{"items": [
            {{"type": "mcq", "question": "...", "options": ["A","B","C","D"], "answer": "B", "explain": "..."}},
            {{"type": "fitb", "question": "Sentence with ___", "answer": "correct phrase", "explain": "..."}}
        ]}}
        Keep options short.
        """
        raw = llm([
            {"role": "system", "content": "You are a quiz generator that outputs strict JSON."},
            {"role": "user", "content": prompt},
        ], temperature=0.2)
        import json
        items = []
        try:
            data = json.loads(raw)
            items = data.get("items", [])
        except Exception:
            st.warning("Quiz parsing failed; showing raw output.")
            st.code(raw)
        st.session_state.quiz_items = items
        st.session_state.quiz_score = 0
        st.session_state.quiz_total = len(items)

    if st.session_state.quiz_items:
        for i, it in enumerate(st.session_state.quiz_items):
            st.markdown(f"**Q{i+1}. {it.get('question','')}**")
            if it.get("type") == "mcq":
                choice = st.radio("Choose one:", it.get("options", []), key=f"mcq_{i}")
                if st.button("Check", key=f"chk_{i}"):
                    correct = it.get("answer")
                    if choice == correct:
                        st.success("Correct! 🎉")
                        st.session_state.quiz_score += 1
                    else:
                        st.error(f"Not quite. Correct: {correct}")
                    st.info(it.get("explain", ""))
            else:
                ans = st.text_input("Your answer", key=f"fitb_{i}")
                if st.button("Check", key=f"chk_{i}"):
                    correct = it.get("answer", "").strip().lower()
                    if ans.strip().lower() == correct:
                        st.success("Correct! 🎉")
                        st.session_state.quiz_score += 1
                    else:
                        st.error(f"Not quite. Example correct: {it.get('answer','')}")
                    st.info(it.get("explain", ""))
        st.markdown(f"### Score: {st.session_state.quiz_score} / {st.session_state.quiz_total}")

# ------------- Mini Challenges Tab -------------
with tabs[4]:
    st.subheader("Mini Challenges (produce then compare)")
    st.markdown("Generate a quick challenge to translate in your own words, then compare with the model.")
    topic = st.text_input("Topic (e.g., campus life, technology, culture)")
    if st.button("Generate challenge") and topic.strip():
        prompt = f"Write a short {src}→{tgt} translation challenge (40–50 words) about {topic}."
        challenge = llm([
            {"role": "system", "content": "You are a creative teacher."},
            {"role": "user", "content": prompt},
        ])
        st.text_area("Challenge text", value=challenge, height=140)
        st.caption("Translate it yourself first, then use the Translate tab to compare.")

# ------------- Assignments Tab (Instructor & Student workflow) -------------
with tabs[5]:
    st.subheader("Assignments — instructor-created exercises with codes")

    ASSIGN_CSV = os.path.join(LOG_DIR, "assignments.csv")
    SUBMIT_CSV = os.path.join(LOG_DIR, "submissions.csv")

    def save_row(path, row):
        df = pd.DataFrame([row])
        if os.path.exists(path):
            old = pd.read_csv(path)
            df = pd.concat([old, df], ignore_index=True)
        df.to_csv(path, index=False)

    def new_code() -> str:
        base = (group_code or "ASSGN").split()[0][:6].upper()
        return base + "-" + str(uuid.uuid4())[:4].upper()

    tabs_asg = st.tabs(["Create (Instructor)", "Do Assignment (Student)", "Submissions (Teacher)"])

    # ---- Create (Instructor gated)
    with tabs_asg[0]:
        if not instructor_unlocked:
            st.info("Instructor tools are locked. Switch role to Instructor and enter the password in the sidebar.")
        else:
            st.markdown("**Instructor:** Create an exercise and share its code with students.")
            as_title = st.text_input("Title")
            as_text = st.text_area("Source text to translate / post-edit", height=150)
            as_mode = st.radio("Mode", ["Translate first (student writes their draft)", "Post-edit given MT (show machine draft)"])
            as_deadline = st.text_input("Deadline (optional, e.g., 2025-11-15 23:59)")
            show_mt = st.checkbox("If Post-edit mode: generate a machine draft now", value=True)
            if st.button("Create assignment"):
                if not as_title or not as_text:
                    st.error("Please fill title and source text.")
                else:
                    code = new_code()
                    mt_draft = ""
                    if as_mode.startswith("Post-edit") and show_mt:
                        mt_draft = llm([
                            {"role": "system", "content": "You are a translator."},
                            {"role": "user", "content": f"Translate from {src} to {tgt}: {as_text}"},
                        ])
                    save_row(ASSIGN_CSV, {
                        "timestamp": now_str(), "code": code, "title": as_title, "mode": as_mode,
                        "source_lang": src, "target_lang": tgt, "domain": domain, "tone": tone,
                        "deadline": as_deadline, "text": as_text, "mt_draft": mt_draft,
                        "instructor": student_name or "", "group": group_code or ""
                    })
                    st.success(f"Assignment created. Code: **{code}**")
                    st.text_input("Copy code", value=code)
                    if os.path.exists(ASSIGN_CSV):
                        df_prev = pd.read_csv(ASSIGN_CSV).tail(10)
                        st.markdown("**Recent assignments (last 10):**")
                        st.dataframe(df_prev[["timestamp","code","title","group","deadline"]])

    # ---- Student do assignment (NO CODE REQUIRED)
    with tabs_asg[1]:
        st.markdown("**Student:** Pick your assignment from your group's list. No code needed.**")

        # Ensure a group is set
        g = (group_code or "").strip()
        if not g:
            st.info("Enter your **Group code** in the sidebar (e.g., ENG201-1) to see assignments.")
        
        assignments_for_group = pd.DataFrame()
        if os.path.exists(ASSIGN_CSV):
            df_all = pd.read_csv(ASSIGN_CSV)
            if g:
                assignments_for_group = df_all[df_all["group"].fillna("") == g].copy()

        if assignments_for_group.empty:
            st.warning("No assignments found for your group yet. Ask your instructor to create one for your group.")
        else:
            # Sort by timestamp and pick latest by default
            try:
                assignments_for_group['timestamp'] = pd.to_datetime(assignments_for_group['timestamp'], errors='coerce')
            except Exception:
                pass
            assignments_for_group = assignments_for_group.sort_values('timestamp')
            options = [f"{r.code} — {r.title} (due: {r.get('deadline','')})" for _, r in assignments_for_group.iterrows()]
            idx_default = len(options) - 1 if options else 0
            pick = st.selectbox("Assignments for my group", options, index=idx_default)

            # Map selection to row
            sel = assignments_for_group.iloc[options.index(pick)] if options else None

            if sel is not None:
                r = sel
                st.markdown(f"### {r['title']}")
                st.caption(f"Mode: {r['mode']} — Deadline: {r.get('deadline','')}")
                st.text_area("Source text", value=r["text"], disabled=True, height=140)

                stud = st.text_area("Your translation (first draft)", height=160)

                mt = r.get("mt_draft", "")
                if r["mode"].startswith("Post-edit"):
                    st.markdown("**Machine draft to post-edit** (hidden until you type your own)")
                    if stud.strip():
                        if not mt:
                            mt = llm([
                                {"role": "system", "content": "You are a translator."},
                                {"role": "user", "content": f"Translate from {src} to {tgt}: {r['text']}"},
                            ])
                        st.text_area("Machine draft", value=mt, height=140)

                post = st.text_area("Post-edited / final version", height=160)

                if st.button("Analyze my errors & create exercises") and post.strip():
                    def analyze_and_exercise(src_text, stud_text, target_lang):
                        rep = llm([
                            {"role": "system", "content": "You are a rigorous translation assessor."},
                            {"role": "user", "content": f"""
                            Source: {src_text}
                            Student translation: {stud_text}
                            Classify errors into: LEXICAL CHOICE, GRAMMAR/SYNTAX, IDIOMATICITY, COLLOCATION, STYLE/REGISTER, PUNCTUATION.
                            For each category, list concrete examples and brief fixes. Then propose 4 short practice items targeting the student's specific weaknesses (mix MCQ/fill-in-rewrite). Output with clear headings and bullets.
                            Output language: {target_lang}.
                            """},
                        ])
                        return rep
                    report = analyze_and_exercise(r["text"], post, tgt)
                    st.markdown(report)

                refl = st.text_area("Short reflection (2–3 sentences): what changed from your first draft and why?", height=100)
                if st.button("Submit assignment"):
                    save_row(SUBMIT_CSV, {
                        "timestamp": now_str(), "code": r["code"], "student": student_name or "",
                        "group": group_code or "", "session": session_id,
                        "first_draft": stud, "final": post, "reflection": refl
                    })
                    st.success("Submitted.")

    # ---- Teacher view (Instructor gated)
    with tabs_asg[2]:
        if not instructor_unlocked:
            st.info("Instructor tools are locked. Switch role to Instructor and enter the password in the sidebar.")
        else:
            if os.path.exists(SUBMIT_CSV):
                df = pd.read_csv(SUBMIT_CSV)
                st.dataframe(df.tail(50))
                st.download_button("Download submissions.csv", data=df.to_csv(index=False).encode("utf-8"), file_name="submissions.csv")
            else:
                st.info("No submissions yet.")
