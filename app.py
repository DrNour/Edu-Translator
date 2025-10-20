# EduTranslator Plus (v3.2)
# English ↔ Arabic translation tutor with Assignments, Instructor Lock, and Clear Fonts

import os
import re
import io
import zipfile
import uuid
from datetime import datetime, time as _time
from typing import Dict, Any, List
import pandas as pd
import streamlit as st
from openai import OpenAI

# Optional dependency for .docx upload
try:
    import docx
except Exception:
    docx = None

# ===================== PAGE CONFIG & STYLE =====================
st.set_page_config(page_title="EduTranslator Plus", page_icon="🗣️", layout="wide")

st.markdown("""
<style>
html, body, [class*="css"] {
    font-family: 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
    color: #1a1a1a;
    font-size: 16px !important;
    line-height: 1.6;
}
h1, h2, h3, h4, h5, h6 { color: #0b0b0b; font-weight: 650; }
.stTextArea textarea, .stTextInput input {
    background-color: #fff !important; color: #000 !important; font-size: 16px !important;
}
.stMarkdown p, label, span { color: #111 !important; font-weight: 450; }
.stButton>button {
    font-size: 16px !important; font-weight: 600;
    border-radius: 6px; color: white !important;
    background-color: #0073e6 !important; border: none;
}
.stButton>button:hover { background-color: #005bb5 !important; }
</style>
""", unsafe_allow_html=True)

st.title("🗣️ EduTranslator Plus")
st.caption("High-contrast fonts and password-protected instructor tools for classroom use.")

# ===================== OPENAI API =====================
api_key = None
try:
    api_key = st.secrets.get("openai", {}).get("api_key")
except Exception:
    pass
api_key = api_key or os.getenv("OPENAI_API_KEY")
if not api_key:
    st.error("OpenAI API key missing. Add it to .streamlit/secrets.toml under [openai].")
    st.stop()

client = OpenAI(api_key=api_key)
MODEL = "gpt-4o-mini"

# ===================== ACCESS CONTROL =====================
app_cfg = st.secrets.get("app", {})
REQUIRED_PASSWORD = app_cfg.get("password")
OPEN_START = app_cfg.get("open_start", "00:00")
OPEN_END = app_cfg.get("open_end", "23:59")

def in_window(start, end):
    try:
        sh, sm = map(int, start.split(":"))
        eh, em = map(int, end.split(":"))
        now = datetime.now().time()
        s, e = _time(sh, sm), _time(eh, em)
        return s <= now <= e if s <= e else now >= s or now <= e
    except Exception:
        return True

if not in_window(OPEN_START, OPEN_END):
    st.error(f"App closed. Open hours: {OPEN_START}–{OPEN_END}.")
    st.stop()

# ===================== HELPERS =====================
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

def now_str(): return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def append_log(path, row):
    df = pd.DataFrame([row])
    if os.path.exists(path):
        old = pd.read_csv(path)
        df = pd.concat([old, df], ignore_index=True)
    df.to_csv(path, index=False)

def llm(messages: List[Dict[str, str]], temperature=0.3):
    try:
        resp = client.chat.completions.create(model=MODEL, messages=messages, temperature=temperature)
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"⚠️ LLM error: {e}"

# ===================== SIDEBAR =====================
with st.sidebar:
    st.header("Settings")

    # Instructor Login
    INSTR_PWD = st.secrets.get("roles", {}).get("instructor_password")
    if "is_instructor" not in st.session_state:
        st.session_state.is_instructor = False

    if not st.session_state.is_instructor:
        with st.expander("Instructor login", expanded=False):
            ipwd = st.text_input("Instructor password", type="password")
            if st.button("Unlock instructor tools"):
                if INSTR_PWD and ipwd == INSTR_PWD:
                    st.session_state.is_instructor = True
                    st.success("Instructor tools unlocked.")
                    st.rerun()
                else:
                    st.error("Wrong instructor password.")
    else:
        st.success("Instructor mode active")
        if st.button("Lock instructor mode"):
            st.session_state.is_instructor = False
            st.rerun()

    # Identity
    student_name = st.text_input("Your name / initials (optional)")
    group_code = st.text_input("Class/Group code (e.g., ENG201-1)")
    st.markdown("---")

    # Language Settings
    auto_detect = st.checkbox("Auto-detect source language", value=True)
    src = st.selectbox("Source language", ["Arabic", "English"], index=0)
    tgt = st.selectbox("Target language", ["English", "Arabic"], index=1)
    if auto_detect:
        st.caption("Auto-detect uses Arabic script to decide source/target.")

    cefr = st.select_slider("CEFR level", options=["A2", "B1", "B2", "C1"], value="B1")
    tone = st.selectbox("Target tone", ["Neutral", "Academic", "Informal", "Professional", "Literary"])
    domain = st.selectbox("Terminology domain", ["General", "Engineering", "Legal", "Media", "Medical", "Business"])
    st.caption(f"🕒 Server time: {datetime.now().strftime('%Y-%m-%d %H:%M')} | Window: {OPEN_START}–{OPEN_END}")

# ===================== TABS =====================
tabs = st.tabs([
    "Translate", "Explain", "Collocations / Idioms", "Assignments", "Teacher Dashboard"
])

# ---------- TRANSLATE ----------
with tabs[0]:
    st.subheader("Translate: Literal vs. Natural")
    text = st.text_area("Enter text", height=160)
    if st.button("Translate") and text.strip():
        system = "You are a bilingual English–Arabic tutor."
        prompt = f"Translate from {src} to {tgt}:\n{text}\nProvide: (1) literal and (2) natural versions."
        out = llm([{"role": "system", "content": system}, {"role": "user", "content": prompt}])
        st.markdown(out)

# ---------- EXPLAIN ----------
with tabs[1]:
    st.subheader("Explain a Word or Phrase")
    lemma = st.text_input("Word or phrase (e.g., albeit, run into)")
    if st.button("Explain") and lemma.strip():
        prompt = f"Explain '{lemma}' for a {cefr} learner with examples and collocations."
        out = llm([{"role": "system", "content": "You are an English–Arabic tutor."}, {"role": "user", "content": prompt}])
        st.markdown(out)

# ---------- COLLOCATIONS / IDIOMS ----------
with tabs[2]:
    st.subheader("Collocations / Idioms")
    term = st.text_input("Enter a word or idiom")
    if st.button("Generate Examples") and term.strip():
        prompt = f"Provide common collocations or idioms for '{term}' in {tgt} with examples and meanings."
        out = llm([{"role": "system", "content": "You are a collocation tutor."}, {"role": "user", "content": prompt}])
        st.markdown(out)

# ---------- ASSIGNMENTS ----------
# ---------- ASSIGNMENTS ----------
with tabs[3]:
    st.subheader("Assignments")

    ASSIGN_CSV = os.path.join(LOG_DIR, "assignments.csv")
    SUBMIT_CSV = os.path.join(LOG_DIR, "submissions.csv")

    def save_row(path, row):
        df = pd.DataFrame([row])
        if os.path.exists(path):
            old = pd.read_csv(path)
            df = pd.concat([old, df], ignore_index=True)
        df.to_csv(path, index=False)

    # Helpers
    def generate_mt(src_text: str, source_lang: str, target_lang: str) -> str:
        return llm([
            {"role": "system", "content": "You are a professional translator."},
            {"role": "user", "content": f"Translate from {source_lang} to {target_lang}:\n{src_text}"}
        ])

    def analyze_and_exercise(src_text: str, student_text: str, target_lang: str) -> str:
        return llm([
            {"role": "system", "content": "You are a rigorous translation assessor and teacher."},
            {"role": "user", "content": f"""
Source:
{src_text}

Student translation:
{student_text}

1) Classify issues using ONLY these labels:
   LEXICAL CHOICE, GRAMMAR/SYNTAX, IDIOMATICITY, COLLOCATION, STYLE/REGISTER, PUNCTUATION.
   Give 1–3 concrete examples per present category with brief fixes.

2) Produce 4 short practice items targeting the student's weaknesses:
   - Mix MCQ / fill-in / rewrite.
   - Keep prompts short.
   - Output language: {target_lang}.

Format with clear headings and bullets.
"""}],
        )

    # =============== INSTRUCTOR ===============
    if st.session_state.is_instructor:
        st.markdown("### 🧑‍🏫 Create Assignment")

        title = st.text_input("Assignment title")
        src_text = st.text_area("Source text", height=140)
        mode = st.radio(
            "Mode",
            ["Translate first (student writes their draft)",
             "Post-edit given MT (show machine draft)"],
            horizontal=False
        )
        # (Optional) generate MT now and store it, so all students see the same draft
        precompute_mt = st.checkbox("Precompute & store machine draft now (recommended for consistency)", value=True)

        # Languages: use sidebar selections (src/tgt)
        # If you want per-assignment languages, add two selectboxes here instead.
        if st.button("Create assignment"):
            if not title.strip() or not src_text.strip():
                st.error("Please provide a title and source text.")
            else:
                mt_draft = ""
                if mode.startswith("Post-edit") and precompute_mt:
                    # Use autodetect if enabled, else the chosen sidebar languages
                    source_lang = src if not auto_detect else ("Arabic" if re.search(r"[\u0600-\u06FF]", src_text) else "English")
                    target_lang = "English" if source_lang == "Arabic" else "Arabic"
                    mt_draft = generate_mt(src_text, source_lang, target_lang)

                save_row(ASSIGN_CSV, {
                    "timestamp": now_str(),
                    "group": group_code or "",
                    "title": title,
                    "text": src_text,
                    "mode": mode,
                    "mt_draft": mt_draft,
                    "source_lang": src,
                    "target_lang": tgt,
                    "instructor": student_name or ""
                })
                st.success(f"Assignment created for group {group_code or '(no group set)'}")
                if mt_draft:
                    with st.expander("Preview stored machine draft"):
                        st.text_area("Stored MT draft", value=mt_draft, height=140, disabled=True)

        # Show last few created
        if os.path.exists(ASSIGN_CSV):
            df_prev = pd.read_csv(ASSIGN_CSV)
            if not df_prev.empty:
                st.markdown("**Recent assignments**")
                cols_to_show = [c for c in ["timestamp", "group", "title", "mode"] if c in df_prev.columns]
                st.dataframe(df_prev.tail(10)[cols_to_show])

        st.markdown("---")

    # =============== STUDENT ===============
    st.markdown("### 🧑‍🎓 Do Assignment")
    g = (group_code or "").strip()
    if not os.path.exists(ASSIGN_CSV):
        st.info("No assignments exist yet.")
    else:
        df = pd.read_csv(ASSIGN_CSV)

        # Backward compatibility: ensure columns exist
        for col in ["mode", "mt_draft", "source_lang", "target_lang"]:
            if col not in df.columns:
                df[col] = ""

        # Filter by group if provided
        if g:
            df = df[df["group"].fillna("") == g]

        if df.empty:
            st.info("No assignments for your group yet.")
        else:
            # Show the newest first by timestamp
            try:
                df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
                df = df.sort_values("timestamp")
            except Exception:
                pass

            options = [f"{r.title}  —  {r.mode or 'Translate first'}" for _, r in df.iterrows()]
            pick = st.selectbox("Assignments for my group", options, index=len(options)-1)
            sel = df.iloc[options.index(pick)]

            # Display assignment
            st.text_area("Source text", value=sel["text"], height=140, disabled=True)
            mode = str(sel["mode"]) if "mode" in sel else "Translate first (student writes their draft)"
            source_lang = str(sel["source_lang"]) if "source_lang" in sel else src
            target_lang = str(sel["target_lang"]) if "target_lang" in sel else tgt


            # Student inputs
            if mode.startswith("Post-edit"):
                st.caption("Mode: Post-edit given MT")

                # Allow student to edit the machine draft
                # If instructor stored mt_draft, show it; otherwise let student generate it
                mt_area_key = "mt_draft_editable"
                mt_default = sel.get("mt_draft") or ""
                colA, colB = st.columns([1,1])
                with colA:
                    if not mt_default and st.button("Generate MT draft"):
                        mt_default = generate_mt(sel["text"], source_lang, target_lang)
                with colB:
                    st.write("")

                mt_editable = st.text_area("Machine draft (editable)", value=mt_default, height=140, key=mt_area_key)
                student_final = st.text_area("Post-edited / final version", height=160, key="post_edit_final")

                # Feedback buttons
                if st.button("Analyze my translation & create exercises"):
                    feedback = analyze_and_exercise(sel["text"], student_final.strip() or mt_editable.strip(), target_lang)
                    st.markdown(feedback)
                    st.session_state["latest_feedback"] = feedback

                if st.button("Submit"):
                    feedback = st.session_state.get("latest_feedback", "")
                    if not feedback:
                        # Auto-generate feedback on submit if they didn't click analyze
                        feedback = analyze_and_exercise(sel["text"], student_final.strip() or mt_editable.strip(), target_lang)
                        st.markdown(feedback)
                        st.session_state["latest_feedback"] = feedback

                    save_row(SUBMIT_CSV, {
                        "timestamp": now_str(),
                        "student": student_name or "",
                        "group": group_code or "",
                        "assignment": sel["title"],
                        "mode": mode,
                        "source_lang": source_lang,
                        "target_lang": target_lang,
                        "mt_editable": mt_editable,
                        "final": student_final,
                        "feedback": feedback
                    })
                    st.success("Submitted! Feedback displayed above and saved to submissions.csv.")

            else:
                st.caption("Mode: Translate first (student writes their draft)")
                student_draft = st.text_area("Your translation (first draft)", height=160)

                if st.button("Analyze my translation & create exercises"):
                    feedback = analyze_and_exercise(sel["text"], student_draft.strip(), target_lang)
                    st.markdown(feedback)
                    st.session_state["latest_feedback"] = feedback

                if st.button("Submit"):
                    feedback = st.session_state.get("latest_feedback", "")
                    if not feedback and student_draft.strip():
                        feedback = analyze_and_exercise(sel["text"], student_draft.strip(), target_lang)
                        st.markdown(feedback)
                        st.session_state["latest_feedback"] = feedback

                    save_row(SUBMIT_CSV, {
                        "timestamp": now_str(),
                        "student": student_name or "",
                        "group": group_code or "",
                        "assignment": sel["title"],
                        "mode": mode,
                        "source_lang": source_lang,
                        "target_lang": target_lang,
                        "final": student_draft,
                        "feedback": feedback
                    })
                    st.success("Submitted! Feedback displayed above and saved to submissions.csv.")

# ---------- TEACHER DASHBOARD ----------
with tabs[4]:
    st.subheader("Teacher Dashboard")
    if not st.session_state.is_instructor:
        st.info("Instructor password required.")
    else:
        path = os.path.join(LOG_DIR, "submissions.csv")
        if os.path.exists(path):
            df = pd.read_csv(path)
            st.dataframe(df.tail(20))
            st.download_button("Download submissions", df.to_csv(index=False).encode(), "submissions.csv")
        else:
            st.info("No submissions yet.")

st.caption("© EduTranslator Plus — for educational use.")


