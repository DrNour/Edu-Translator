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

    if st.session_state.is_instructor:
        st.markdown("### 🧑‍🏫 Create Assignment")
        title = st.text_input("Assignment title")
        src_text = st.text_area("Source text", height=120)
        if st.button("Create assignment") and title.strip() and src_text.strip():
            code = group_code or "ALL"
            save_row(ASSIGN_CSV, {
                "timestamp": now_str(), "group": group_code, "title": title, "text": src_text
            })
            st.success(f"Assignment created for group {group_code}")
    else:
        st.markdown("### 🧑‍🎓 Do Assignment")
        if os.path.exists(ASSIGN_CSV):
            df = pd.read_csv(ASSIGN_CSV)
            g = (group_code or "").strip()
            df = df[df["group"] == g] if g else df
            if df.empty:
                st.info("No assignments for your group yet.")
            else:
                options = [f"{r.title}" for _, r in df.iterrows()]
                pick = st.selectbox("Assignments for my group", options)
                sel = df[df["title"] == pick].iloc[0]
                st.text_area("Source text", value=sel["text"], height=120, disabled=True)
                translation = st.text_area("Your translation", height=160)
                if st.button("Submit"):
                    save_row(SUBMIT_CSV, {
                        "timestamp": now_str(), "student": student_name, "group": group_code,
                        "assignment": sel["title"], "translation": translation
                    })
                    st.success("Submitted!")

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
