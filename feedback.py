# feedback.py
# ============================================================
# Smart Atlas — Trip Feedback Module
# Multi-step feedback form with SQLite storage
# + Excel logging via excel_logger.py
# NOTE: st.set_page_config() is intentionally NOT called here
#       because this module is imported/called from log_p.py
#       which already sets page config.
# ============================================================

import streamlit as st
import sqlite3
import re
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# ── Excel logger (fail-safe) ──────────────────────────────────
try:
    import excel_logger as _xl
    _XL_OK = True
except ImportError:
    _XL_OK = False


# ── Database setup ────────────────────────────────────────────
_DB_PATH = "feedback.db"

def _get_db():
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
    cur  = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            name            TEXT,
            email           TEXT,
            contact         TEXT,
            time_rating     INTEGER,
            route_rating    INTEGER,
            weather_rating  INTEGER,
            planning_rating INTEGER,
            overall_rating  INTEGER,
            expectation     TEXT,
            reuse           TEXT,
            recommend       TEXT,
            why_not         TEXT,
            suggestions     TEXT,
            submitted_at    TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    try:
        cur.execute("ALTER TABLE feedback ADD COLUMN why_not TEXT")
    except sqlite3.OperationalError:
        pass
    conn.commit()
    return conn, cur


# ── Validation helpers ────────────────────────────────────────
def _valid_email(email: str) -> bool:
    return bool(re.match(r"[^@]+@[^@]+\.[^@]+", email.strip()))

def _valid_contact(contact: str) -> bool:
    return contact.strip().isdigit() and len(contact.strip()) == 10


# ── Star rating widget ────────────────────────────────────────
def _star_rating(label: str, key: str, default: int = 3) -> int:
    options = ["⭐", "⭐⭐", "⭐⭐⭐", "⭐⭐⭐⭐", "⭐⭐⭐⭐⭐"]
    val     = options[max(0, min(default - 1, 4))]
    choice  = st.select_slider(label, options=options, value=val, key=key)
    return options.index(choice) + 1


# ── CSS ───────────────────────────────────────────────────────
def _inject_feedback_css():
    st.markdown("""
    <style>
    .stApp {
        font-family: 'Segoe UI', sans-serif;
    }
    h1,h2,h3,h4 { color:#f1f5f9 !important; font-weight:700 !important; }
    .stCaption,small { color:rgba(255,255,255,0.55) !important; }
    .feedback-card {
        background:rgba(255,255,255,0.08);
        backdrop-filter:blur(14px);
        border:1px solid rgba(255,255,255,0.14);
        border-radius:18px; padding:22px 26px; margin-bottom:18px;
        box-shadow:0 8px 32px rgba(0,0,0,0.28);
    }
    .stButton > button {
        background:linear-gradient(135deg,#F6A81A,#FFc84D) !important;
        color:#1a1a1a !important; border:none !important;
        border-radius:12px !important; padding:10px 18px !important;
        font-weight:700 !important; width:100% !important;
        transition:transform .15s,box-shadow .15s !important;
    }
    .stButton > button:hover {
        transform:translateY(-2px) !important;
        box-shadow:0 6px 20px rgba(246,168,26,0.40) !important;
    }
    .stFormSubmitButton > button {
        background:linear-gradient(135deg,#1B3B8B,#2D55C7) !important;
        color:#fff !important; border:none !important;
        border-radius:12px !important; padding:10px 18px !important;
        font-weight:700 !important; width:100% !important;
    }
    .stTextInput input, .stTextArea textarea {
        background:rgba(255,255,255,0.10) !important;
        border:1px solid rgba(255,255,255,0.22) !important;
        border-radius:10px !important; color:#f1f5f9 !important;
        padding:10px 14px !important;
    }
    .stTextInput label, .stTextArea label, .stRadio label,
    .stSelectbox label { color:rgba(255,255,255,0.80) !important; font-size:.88rem !important; }
    .stAlert { border-radius:12px !important; }
    hr { border-color:rgba(255,255,255,0.14) !important; margin:18px 0 !important; }
    .step-progress { display:flex; gap:10px; align-items:center; margin-bottom:20px; }
    .step-dot {
        width:32px; height:32px; border-radius:50%;
        display:flex; align-items:center; justify-content:center;
        font-size:.8rem; font-weight:700; color:#fff;
    }
    .step-dot.active   { background:#F6A81A; }
    .step-dot.done     { background:#22C55E; }
    .step-dot.inactive { background:rgba(255,255,255,0.20); }
    .step-line { flex:1; height:2px; background:rgba(255,255,255,0.20); border-radius:2px; }
    .step-line.done { background:#22C55E; }
    </style>
    """, unsafe_allow_html=True)


# ── Step progress UI ──────────────────────────────────────────
def _render_steps(current: int):
    steps = ["👤 Details", "⭐ Ratings", "💬 Feedback"]
    html  = '<div class="step-progress">'
    for i, label in enumerate(steps, start=1):
        cls = "active" if i == current else ("done" if i < current else "inactive")
        html += f'<div class="step-dot {cls}">{i if cls != "done" else "✓"}</div>'
        if i < len(steps):
            line_cls = "done" if i < current else ""
            html += f'<div class="step-line {line_cls}"></div>'
    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)


# ── Main feedback function ────────────────────────────────────
def feedback_page():
    try:
        import theme
        theme.apply_global_theme()
    except ImportError:
        pass
    _inject_feedback_css()

    st.markdown("# 🌍 Trip Feedback — Smart Atlas")
    st.caption("Your feedback helps us improve. It takes less than 2 minutes!")
    st.markdown("---")

    for k, v in [("fb_step", 1), ("fb_submitted", False), ("fb_data", {})]:
        if k not in st.session_state:
            st.session_state[k] = v

    if st.session_state.fb_submitted:
        _show_thank_you()
        return

    _render_steps(st.session_state.fb_step)
    st.markdown('<div class="feedback-card">', unsafe_allow_html=True)

    if st.session_state.fb_step == 1:
        _step_user_details()
    elif st.session_state.fb_step == 2:
        _step_ratings()
    elif st.session_state.fb_step == 3:
        _step_feedback_text()

    st.markdown('</div>', unsafe_allow_html=True)


def _step_user_details():
    st.subheader("👤 Step 1 — Your Details")
    default_email = ""
    if st.session_state.get("user"):
        default_email = st.session_state.user.get("email", "")

    with st.form("fb_step1"):
        c1, c2  = st.columns(2)
        name    = c1.text_input("Full Name",           placeholder="Rahul Sharma",  key="fb_name_in")
        email   = c2.text_input("Email",               value=default_email,         key="fb_email_in")
        contact = c1.text_input("Contact (10 digits)", placeholder="98XXXXXXXX",   key="fb_contact_in")
        submit  = st.form_submit_button("Next →")

    if submit:
        errs = []
        if not name.strip() or not email.strip() or not contact.strip():
            errs.append("Please fill all required fields.")
        if email and not _valid_email(email):
            errs.append("Enter a valid email address.")
        if contact and not _valid_contact(contact):
            errs.append("Contact must be exactly 10 digits.")
        if errs:
            for e in errs:
                st.warning(f"⚠️ {e}")
        else:
            st.session_state.fb_data.update({
                "name": name.strip(), "email": email.strip(), "contact": contact.strip()
            })
            st.session_state.fb_step = 2
            st.rerun()


def _step_ratings():
    st.subheader("⭐ Step 2 — Rate Your Experience")
    with st.form("fb_step2"):
        time_r     = _star_rating("How much time/effort did Smart Atlas save you?",   "fb_time",    3)
        route_r    = _star_rating("How accurate were the suggested routes?",          "fb_route",   3)
        weather_r  = _star_rating("How useful were the weather updates?",             "fb_weather", 3)
        planning_r = _star_rating("How satisfied with the trip planning process?",    "fb_plan",    3)
        overall_r  = _star_rating("Overall experience with Smart Atlas?",             "fb_overall", 3)
        submit     = st.form_submit_button("Next →")

    if submit:
        st.session_state.fb_data.update({
            "time_rating": time_r, "route_rating": route_r,
            "weather_rating": weather_r, "planning_rating": planning_r,
            "overall_rating": overall_r,
        })
        st.session_state.fb_step = 3
        st.rerun()

    st.markdown("---")
    if st.button("← Back", key="fb_back_to_1"):
        st.session_state.fb_step = 1
        st.rerun()


def _step_feedback_text():
    st.subheader("💬 Step 3 — Share Your Thoughts")
    with st.form("fb_step3"):
        expectation = st.text_input(
            "Did Smart Atlas meet your travel expectations?",
            placeholder="Yes, mostly / No, because...", key="fb_exp"
        )
        reuse = st.radio("Would you use Smart Atlas again?",
                         ["Yes", "No", "Maybe"], key="fb_reuse")
        recommend = st.text_input(
            "Would you recommend Smart Atlas to others?",
            placeholder="Yes / No / Depends", key="fb_rec"
        )
        why_not = ""
        if reuse == "No":
            why_not = st.text_area(
                "Why not? (optional)", placeholder="Tell us what went wrong", key="fb_whynot"
            )
        suggestions = st.text_area(
            "Suggestions for improvement (optional)",
            placeholder="What would you like to see next?", key="fb_sugg"
        )
        submit = st.form_submit_button("Submit Feedback ✅")

    if submit:
        d = st.session_state.fb_data

        # ── 1. Save to SQLite (original logic — unchanged) ────
        conn, cur = _get_db()
        sqlite_ok = False
        try:
            cur.execute("""
                INSERT INTO feedback
                  (name,email,contact,time_rating,route_rating,weather_rating,
                   planning_rating,overall_rating,expectation,reuse,recommend,
                   why_not,suggestions,submitted_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                d.get("name"), d.get("email"), d.get("contact"),
                d.get("time_rating"), d.get("route_rating"), d.get("weather_rating"),
                d.get("planning_rating"), d.get("overall_rating"),
                expectation, reuse, recommend, why_not, suggestions,
                datetime.now().isoformat(),
            ))
            conn.commit()
            sqlite_ok = True
        except sqlite3.Error as e:
            st.error(f"❌ Could not save feedback: {e}")
        finally:
            conn.close()

        # ── 2. Save to Excel ──────────────────────────────────
        if sqlite_ok and _XL_OK:
            try:
                parts = []
                if expectation: parts.append(f"Expectation: {expectation}")
                if recommend:   parts.append(f"Recommend: {recommend}")
                if why_not:     parts.append(f"Why not reuse: {why_not}")
                if suggestions: parts.append(f"Suggestions: {suggestions}")
                _xl.log_feedback(
                    email=d.get("email", "anonymous"),
                    rating=d.get("overall_rating", 0),
                    comment=" | ".join(parts),
                )
            except Exception as xe:
                logger.error("Excel feedback log failed: %s", xe)

        # ── 3. Mark submitted ─────────────────────────────────
        if sqlite_ok:
            st.session_state.fb_submitted = True
            st.rerun()

    st.markdown("---")
    if st.button("← Back", key="fb_back_to_2"):
        st.session_state.fb_step = 2
        st.rerun()


def _show_thank_you():
    st.success("✅ Feedback Submitted Successfully!")
    st.balloons()
    st.markdown("### 🎉 Thank You for Your Valuable Feedback!")
    st.caption("Your responses help make Smart Atlas better for every traveller.")
    d = st.session_state.get("fb_data", {})
    if d:
        st.markdown('<div class="feedback-card">', unsafe_allow_html=True)
        st.markdown(f"**👤 Name:** {d.get('name', '—')}")
        st.markdown(f"**📧 Email:** {d.get('email', '—')}")
        st.markdown(f"**⭐ Overall Rating:** {'⭐' * d.get('overall_rating', 0)}")
        st.markdown('</div>', unsafe_allow_html=True)
    if st.button("📝 Submit Another Response", key="fb_another"):
        for k in ["fb_step", "fb_submitted", "fb_data"]:
            st.session_state.pop(k, None)
        st.rerun()


# ── Standalone entry point ────────────────────────────────────
if __name__ == "__main__":
    st.set_page_config(page_title="Smart Atlas Feedback", layout="centered")
    feedback_page()
