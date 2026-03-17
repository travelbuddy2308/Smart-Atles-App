# log_p.py
# ============================================================
# Smart Atlas — Main Entry Point
# Handles: Auth (Login / Signup / OTP / Reset),
#          Session management, Routing, Sidebar, AI Chatbot
# ============================================================

import streamlit as st
import mysql.connector
import hashlib
import re
from datetime import date, datetime
import random
import time
import bcrypt
import base64
import logging
from collections import deque

import theme
import map_p
import itinerary_generator
import fh
import home

try:
    import feedback as _feedback
    _FEEDBACK_OK = True
except ImportError:
    _FEEDBACK_OK = False

logger = logging.getLogger(__name__)

# ── Activity logger (login + search tracking) ─────────────────
try:
    import db_logger as _db_log
    _DB_LOG_OK = True
except ImportError:
    _DB_LOG_OK = False

# ── Excel logger (all form data → smart_atlas_data.xlsx) ───────
try:
    import excel_logger as _xl
    _XL_OK = True
except ImportError:
    _XL_OK = False

# Configure logging to file
logging.basicConfig(
    filename="app.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)

# ── Try imports gracefully ────────────────────────────────────
try:
    from textblob import TextBlob
    _TEXTBLOB_OK = True
except ImportError:
    _TEXTBLOB_OK = False

# ── Optional TTS ─────────────────────────────────────────────
try:
    from gtts import gTTS
    _GTTS_OK = True
except ImportError:
    _GTTS_OK = False

# ── langdetect (optional) ─────────────────────────────────────
try:
    from langdetect import detect as _detect_lang
    _LANGDETECT_OK = True
except ImportError:
    _LANGDETECT_OK = False
    def _detect_lang(text): return "en"

# ── Async HTTP for batched API calls ─────────────────────────
try:
    import httpx
    _HTTPX_OK = True
except ImportError:
    _HTTPX_OK = False

# ── In-memory caches ─────────────────────────────────────────
_COST_CACHE      = {}
_SENTIMENT_CACHE = {}
_GEO_CACHE       = {}


def _cache_sentiment(text: str) -> float:
    key = hash(text[:200])
    if key in _SENTIMENT_CACHE:
        return _SENTIMENT_CACHE[key]
    score = 0.0
    if _TEXTBLOB_OK:
        try:
            score = TextBlob(text).sentiment.polarity
        except Exception:
            pass
    _SENTIMENT_CACHE[key] = score
    return score


def _cache_cost(trip_key: str, compute_fn):
    if trip_key not in _COST_CACHE:
        _COST_CACHE[trip_key] = compute_fn()
    return _COST_CACHE[trip_key]

# ── Page config ───────────────────────────────────────────────
st.set_page_config(
    page_title="Smart Atlas — AI Travel Planner",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="auto",
)

# ── Asset paths ───────────────────────────────────────────────
_ASSET_DIR = "asset"
BG_PATH    = f"{_ASSET_DIR}/dark_mountain.png"
LOGO_PATH  = f"{_ASSET_DIR}/logo.jpeg"

def _img_to_b64(path: str) -> str:
    try:
        with open(path, "rb") as f:
            data = base64.b64encode(f.read()).decode()
        ext  = path.rsplit(".", 1)[-1].lower()
        mime = "jpeg" if ext in ("jpg", "jpeg") else ext
        return f"data:image/{mime};base64,{data}"
    except FileNotFoundError:
        return ""

BG_B64   = _img_to_b64(BG_PATH)
LOGO_B64 = _img_to_b64(LOGO_PATH)


# ── CSS injection ─────────────────────────────────────────────
def inject_css():
    st.markdown(f"""
    <style>

    [data-testid="stAppViewContainer"] {{
        overflow-y: auto !important;
    }}
    .block-container {{
        padding-bottom: 4rem !important;
        max-width: 100% !important;
    }}

    .stApp {{
        font-family: 'Inter', system-ui, sans-serif !important;
    }}

    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Space+Grotesk:wght@500;600;700&display=swap');


    html {{
        margin: 0; padding: 0;
        overflow: visible !important;
    }}
    body {{
        margin: 0; padding: 0;
        overflow-x: clip !important;
        font-family: 'Inter', 'Segoe UI', system-ui, sans-serif !important;
    }}

    .stApp {{
        min-height: 100vh;
        height: auto !important;
        font-family: 'Inter', system-ui, sans-serif !important;
    }}

    section.main {{
        height: auto !important;
        background: rgba(5, 10, 35, 0.72) !important;
    }}
    section.main > div {{
        height: auto !important;
    }}
    .stMain, [data-testid="stMain"],
    [data-testid="stAppViewContainer"],
    [data-testid="stMainBlockContainer"] {{
        height: auto !important;
        min-height: 0 !important;
        background: transparent !important;
    }}

    .block-container {{
        padding: 1.5rem 1.2rem 4rem !important;
        max-width: 1140px !important;
        margin: 0 auto !important;
        height: auto !important;
        min-height: 0 !important;
        width: 100% !important;
    }}

    /* Reset block padding removed to fix text overlap */

    [data-testid="stForm"] > div {{ gap: 6px !important; row-gap: 6px !important; }}
    [data-testid="stForm"] {{
        border: none !important;
        padding: 0 !important;
        background: transparent !important;
        box-shadow: none !important;
    }}
    [data-testid="InputInstructions"] {{ display: none !important; }}
    [data-testid="stFormSubmitButton"] button:focus {{
        outline: none !important;
        box-shadow: 0 0 0 3px rgba(246,168,26,0.25) !important;
    }}

    .stTextInput, .stSelectbox, .stNumberInput, .stDateInput,
    .stRadio, .stMultiSelect, .stTextArea, .stToggle,
    .stButton, .stAlert, .stMetric, .stCheckbox, .stSlider {{
        margin: 0 0 5px 0 !important;
    }}
    .stCheckbox {{ margin: 2px 0 3px 0 !important; }}
    .stSlider   {{ margin: 0 0 6px 0 !important; }}
    hr {{ margin: 8px 0 !important; border-color: rgba(255,255,255,0.12) !important; }}

    h1, h2, h3, h4 {{
        font-family: 'Space Grotesk', 'Inter', sans-serif !important;
        color: #F1F5F9 !important;
        margin: 0 0 4px 0 !important;
        line-height: 1.2 !important;
    }}
    h1 {{ font-size: 1.5rem !important; font-weight: 700 !important; }}
    h2 {{ font-size: 1.2rem !important; font-weight: 700 !important; }}
    h3 {{ font-size: 1.0rem !important; font-weight: 600 !important; }}
    h4 {{ font-size: 0.90rem !important; font-weight: 600 !important; }}
    p  {{ color: #CBD5E1 !important; font-size: 0.87rem !important; margin: 0 !important; }}
    .stCaption, small {{
        color: rgba(255,255,255,0.55) !important;
        font-size: 0.74rem !important;
        line-height: 1.4 !important;
    }}
    strong {{ color: #F1F5F9 !important; }}

    section.main .stTextInput input,
    section.main .stTextInput > div > div > input,
    section.main div[data-baseweb="input"] input {{
        background: rgba(17, 27, 53, 0.8) !important;
        border: 1.5px solid rgba(148, 163, 184, 0.4) !important;
        border-radius: 9px !important;
        color: #ffffff !important;
        caret-color: #F6A81A !important;
        -webkit-text-fill-color: #ffffff !important;
        font-size: 0.95rem !important;
    }}
    section.main .stTextInput input::placeholder,
    section.main div[data-baseweb="input"] input::placeholder {{
        color: rgba(255, 255, 255, 0.45) !important;
        -webkit-text-fill-color: rgba(255, 255, 255, 0.45) !important;
    }}
    section.main .stTextInput input:focus,
    section.main div[data-baseweb="input"] input:focus {{
        border-color: #F6A81A !important;
        box-shadow: 0 0 0 3px rgba(246,168,26,0.14) !important;
        background: #162040 !important;
        -webkit-text-fill-color: #E8EDF8 !important;
    }}
    section.main div[data-baseweb="input"] {{
        background: rgba(17, 27, 53, 0.8) !important;
        border-radius: 9px !important;
    }}
    section.main .stSelectbox > div > div,
    section.main [data-baseweb="select"] > div {{
        background: rgba(17, 27, 53, 0.8) !important;
        border: 1.5px solid rgba(148, 163, 184, 0.4) !important;
        border-radius: 9px !important;
        color: #ffffff !important;
    }}
    section.main .stNumberInput input {{
        background: rgba(17, 27, 53, 0.8) !important;
        color: #ffffff !important;
        -webkit-text-fill-color: #ffffff !important;
        border: 1.5px solid rgba(148, 163, 184, 0.4) !important;
    }}
    section.main .stTextInput label,
    section.main .stSelectbox label,
    section.main .stNumberInput label,
    section.main .stDateInput label,
    section.main .stRadio label,
    section.main .stSlider label {{
        color: rgba(255, 255, 255, 0.9) !important;
        font-size: 0.8rem !important;
        font-weight: 700 !important;
        text-transform: uppercase !important;
        letter-spacing: 0.8px !important;
        text-shadow: 0 1px 3px rgba(0,0,0,0.8);
    }}

    [data-testid="stSidebar"] {{
        background: linear-gradient(180deg, rgba(4,10,35,0.98) 0%, rgba(7,15,50,0.97) 100%) !important;
        backdrop-filter: blur(28px) !important;
        -webkit-backdrop-filter: blur(28px) !important;
        border-right: 1px solid rgba(255,255,255,0.06) !important;
        width: 210px !important; min-width: 210px !important; max-width: 210px !important;
    }}
    [data-testid="stSidebar"] > div:first-child {{
        padding: 12px 10px 12px 14px !important;
    }}
    [data-testid="stSidebar"] [data-testid="stVerticalBlock"],
    [data-testid="stSidebar"] .stVerticalBlock {{
        gap: 0 !important; row-gap: 0 !important;
    }}
    [data-testid="stSidebar"] [data-testid="stVerticalBlock"] > div,
    [data-testid="stSidebar"] .stVerticalBlock > div {{
        margin: 0 !important; padding: 0 !important; gap: 0 !important;
    }}
    [data-testid="stSidebar"] .element-container {{
        margin: 0 !important; padding: 0 !important;
    }}
    [data-testid="stSidebar"] .stMarkdown {{
        margin: 0 !important; padding: 0 !important;
    }}
    [data-testid="stSidebar"] .stRadio > label {{
        color: rgba(255,255,255,0.35) !important;
        font-size: 0.58rem !important; font-weight: 700 !important;
        text-transform: uppercase !important; letter-spacing: 1.4px !important;
        margin: 6px 0 2px 2px !important; padding: 0 !important;
        display: block !important;
    }}
    [data-testid="stSidebar"] .stRadio > div {{
        display: flex !important; flex-direction: column !important;
        gap: 0 !important; row-gap: 0 !important;
    }}
    [data-testid="stSidebar"] .stRadio label {{
        color: rgba(255,255,255,0.72) !important;
        font-size: 0.85rem !important; font-weight: 500 !important;
        padding: 6px 8px 6px 10px !important;
        border-radius: 7px !important;
        margin: 0 0 1px 0 !important;
        line-height: 1.25 !important; min-height: 0 !important;
        transition: background 0.1s, color 0.1s !important;
        display: block !important;
        cursor: pointer !important;
    }}
    [data-testid="stSidebar"] .stRadio label:hover {{
        background: rgba(255,255,255,0.08) !important;
        color: #fff !important;
    }}
    [data-testid="stSidebar"] [data-baseweb="radio"] {{
        display: none !important;
    }}
    [data-testid="stSidebar"] .stCaption,
    [data-testid="stSidebar"] small {{
        color: rgba(255,255,255,0.38) !important;
        font-size: 0.70rem !important; line-height: 1.4 !important;
    }}
    [data-testid="stSidebar"] hr {{
        border-color: rgba(255,255,255,0.07) !important; margin: 6px 0 !important;
    }}
    [data-testid="stSidebar"] .stButton {{ margin: 0 !important; }}
    [data-testid="stSidebar"] .stToggle {{ margin: 0 !important; }}

    #MainMenu, footer, header,
    [data-testid="stToolbar"],
    [data-testid="stDecoration"],
    [data-testid="stStatusWidget"] {{ display: none !important; }}

    .stAlert {{ border-radius: 9px !important; font-size: 0.83rem !important; padding: 8px 12px !important; }}

    [data-testid="stExpander"] summary {{
        background: rgba(255,255,255,0.06) !important;
        border: 1px solid rgba(255,255,255,0.10) !important;
        border-radius: 9px !important; color: #E2E8F0 !important;
        font-weight: 600 !important; font-size: 0.86rem !important;
        padding: 8px 12px !important;
    }}
    [data-testid="stExpander"] [data-testid="stExpanderDetails"] {{
        border: 1px solid rgba(255,255,255,0.08) !important;
        border-top: none !important; border-radius: 0 0 9px 9px !important;
        background: rgba(0,0,0,0.15) !important; padding: 8px 12px !important;
    }}

    ::-webkit-scrollbar {{ width: 4px; height: 4px; }}
    ::-webkit-scrollbar-track {{ background: transparent; }}
    ::-webkit-scrollbar-thumb {{ background: rgba(255,255,255,0.18); border-radius: 4px; }}

    /* ── LINK BUTTONS — external booking/redirect links ── */
    [data-testid="stLinkButton"] a,
    [data-testid="stLinkButton"] > a {{
        background: rgba(255,255,255,0.07) !important;
        border: 1px solid rgba(255,255,255,0.18) !important;
        border-radius: 9px !important;
        color: #E2E8F0 !important;
        font-size: 0.82rem !important;
        font-weight: 600 !important;
        padding: 8px 14px !important;
        text-decoration: none !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        gap: 5px !important;
        transition: background .14s, border-color .14s, color .14s !important;
        cursor: pointer !important;
        width: 100% !important;
        box-sizing: border-box !important;
    }}
    [data-testid="stLinkButton"] a:hover {{
        background: rgba(246,168,26,0.16) !important;
        border-color: rgba(246,168,26,0.48) !important;
        color: #FCD34D !important;
        text-decoration: none !important;
    }}

    /* ── AUTH cards ── */
    [data-testid="column"]:first-child {{
        display: flex !important;
        flex-direction: column !important;
        justify-content: center !important;
        align-items: center !important;
        min-height: 85vh !important;
        padding: 40px 32px !important;
    }}

    @keyframes slideUp {{ from{{opacity:0;transform:translateY(24px)}} to{{opacity:1;transform:translateY(0)}} }}

    .sa-card {{
        width: 100%; max-width: 460px; margin: 0 auto;
        border-radius: 20px;
        padding: 32px 36px 28px;
        animation: slideUp .4s cubic-bezier(.16,1,.3,1) both;
    }}

    .sa-card-logo {{ display:flex; align-items:center; gap:10px; margin-bottom:12px; }}
    .sa-card-logo img {{ width:38px; border-radius:8px; }}
    .sa-card-logo-name {{ font-size:1.1rem; font-weight:800; line-height:1; }}
    .sa-card-logo-name span {{ color:#F6A81A; }}
    .sa-form-title {{ font-size:1.28rem; font-weight:800; margin-bottom:4px; line-height:1.3; }}
    .sa-form-sub {{ font-size:.82rem; margin-bottom:16px; line-height:1.5; }}

    .sa-bar {{ height:4px; border-radius:4px; margin-top:4px; transition:width .4s,background .4s; }}
    .sa-bar-label {{ font-size:.68rem; font-weight:600; margin-top:2px; }}

    .sa-otp-box {{
        background:linear-gradient(135deg,#EFF6FF,#DBEAFE);
        border:1px solid #BFDBFE; border-radius:10px;
        padding:12px 16px; font-size:.84rem; color:#1E40AF;
        margin-bottom:12px; text-align:center;
    }}

    .sa-left-content {{
        display:flex; flex-direction:column; align-items:center;
        text-align:center; gap:0; padding:40px 24px;
    }}
    .sa-logo-img {{
        width:96px; height:96px; object-fit:contain; border-radius:20px;
        display:block; margin:0 auto 20px auto;
        filter:drop-shadow(0 6px 20px rgba(0,0,0,.45));
        animation:floatLogo 4s ease-in-out infinite;
    }}
    @keyframes floatLogo {{ 0%,100%{{transform:translateY(0)}} 50%{{transform:translateY(-8px)}} }}

    .sa-brand-title {{
        font-size:2.8rem; font-weight:800; color:#FFFFFF; line-height:1;
        letter-spacing:-1px; margin:0 0 6px 0;
        font-family:'Space Grotesk','Inter',sans-serif;
    }}
    .sa-brand-title span {{ color:#F6A81A; }}
    .sa-brand-sub {{
        font-size:0.82rem; color:rgba(255,255,255,0.42);
        font-weight:500; letter-spacing:2px; text-transform:uppercase;
        margin:0 0 24px 0;
    }}
    .sa-tagline {{
        font-size:.88rem; color:rgba(255,255,255,0.88);
        max-width:290px; line-height:1.9; margin:0 0 24px 0;
        background:rgba(255,255,255,0.07);
        padding:14px 20px; border-radius:12px;
        border:1px solid rgba(255,255,255,0.13);
        text-shadow: 0 1px 8px rgba(0,0,0,0.5);
    }}
    .sa-pills {{
        display:flex; gap:8px; flex-wrap:wrap; justify-content:center;
        max-width:300px;
    }}
    .sa-pill {{
        background:rgba(246,168,26,0.10);
        border:1px solid rgba(246,168,26,0.28);
        color:rgba(255,255,255,0.80); padding:6px 14px;
        border-radius:100px; font-size:.76rem; font-weight:600;
        transition: all .14s; cursor:default;
    }}
    .sa-pill:hover {{
        background:rgba(246,168,26,0.18);
        border-color:rgba(246,168,26,0.50);
        color:#fff;
    }}
    .sa-stat-strip {{
        display:flex; gap:20px; margin-top:28px;
        padding-top:24px; border-top:1px solid rgba(255,255,255,0.08);
        width:100%; justify-content:center;
    }}
    .sa-stat {{
        display:flex; flex-direction:column; align-items:center; gap:2px;
    }}
    .sa-stat-num {{
        font-size:1.1rem; font-weight:800; color:#F6A81A;
        font-family:'Space Grotesk',sans-serif;
    }}
    .sa-stat-lab {{
        font-size:0.65rem; color:rgba(255,255,255,0.38);
        text-transform:uppercase; letter-spacing:0.8px; font-weight:600;
    }}

    /* login card scoped to right column */
    [data-testid="stMain"] [data-testid="column"]:last-child {{
        background: #FFFFFF;
        border-radius: 20px;
        padding: 36px 32px 28px !important;
        box-shadow: 0 20px 60px rgba(10,20,60,0.18), 0 4px 16px rgba(0,0,0,0.07);
        border: 1px solid #E8ECF4;
        margin-top: 40px;
        align-self: flex-start !important;
    }}
    [data-testid="stMain"] [data-testid="column"]:last-child .stTextInput input {{
        background: #F9FAFB !important;
        border: 1.5px solid #D1D5DB !important;
        border-radius: 9px !important;
        color: #111827 !important;
        -webkit-text-fill-color: #111827 !important;
        padding: 10px 14px !important;
        font-size: .92rem !important;
    }}
    [data-testid="stMain"] [data-testid="column"]:last-child .stTextInput input::placeholder {{
        color: #9CA3AF !important;
        -webkit-text-fill-color: #9CA3AF !important;
    }}
    [data-testid="stMain"] [data-testid="column"]:last-child .stTextInput input:focus {{
        border-color: #1B3B8B !important;
        box-shadow: 0 0 0 3px rgba(27,59,139,0.12) !important;
        background: #fff !important;
    }}
    [data-testid="stMain"] [data-testid="column"]:last-child .stTextInput label {{
        color: #374151 !important;
        font-size: .70rem !important;
        font-weight: 700 !important;
        text-transform: uppercase !important;
        letter-spacing: .5px !important;
        margin-bottom: 3px !important;
    }}
    [data-testid="stMain"] [data-testid="column"]:last-child [data-testid="stFormSubmitButton"] button {{
        width: 100% !important;
        background: linear-gradient(135deg, #F6A81A 0%, #FFD060 100%) !important;
        color: #1a1000 !important;
        border: none !important;
        border-radius: 10px !important;
        padding: 13px 0 !important;
        font-weight: 800 !important;
        font-size: .97rem !important;
        margin-top: 10px !important;
        transition: transform .13s, box-shadow .13s !important;
        box-shadow: 0 4px 16px rgba(246,168,26,0.38) !important;
    }}
    [data-testid="stMain"] [data-testid="column"]:last-child [data-testid="stFormSubmitButton"] button:hover {{
        transform: translateY(-1px) !important;
        box-shadow: 0 7px 22px rgba(246,168,26,0.52) !important;
    }}
    [data-testid="stMain"] [data-testid="column"]:last-child .stButton button {{
        width: 100% !important;
        background: transparent !important;
        color: #374151 !important;
        border: 1.5px solid #E5E7EB !important;
        border-radius: 10px !important;
        padding: 9px 0 !important;
        font-weight: 600 !important;
        font-size: .88rem !important;
        transition: border-color .14s, color .14s !important;
        box-shadow: none !important;
    }}
    [data-testid="stMain"] [data-testid="column"]:last-child .stButton button:hover {{
        border-color: #1B3B8B !important;
        color: #1B3B8B !important;
    }}
    [data-testid="stMain"] [data-testid="column"]:first-child {{
        background: transparent !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        padding: 40px 24px !important;
    }}
    </style>
    """, unsafe_allow_html=True)

    theme.apply_global_theme()

# ── Database ──────────────────────────────────────────────────
def get_db() -> mysql.connector.MySQLConnection | None:
    try:
        conn = mysql.connector.connect(
            host=st.secrets.get("db", {}).get("host", "localhost"),
            user=st.secrets.get("db", {}).get("user", "root"),
            password=st.secrets.get("db", {}).get("password", ""),
            database=st.secrets.get("db", {}).get("database", "travel_app"),
        )
        return conn
    except mysql.connector.Error as e:
        logger.error("Database connection failed: %s", e)
        st.warning("⚠️ Database unavailable. Some features may not work.")
        return None

get_db_connection = get_db


# ── Password utilities ────────────────────────────────────────
def hash_pw(pw: str) -> str:
    return bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def check_pw(pw: str, h) -> bool:
    if not h:
        return False
    try:
        pw_bytes   = pw.encode("utf-8")
        hash_bytes = h.strip() if isinstance(h, bytes) else h.strip().encode("utf-8")
        return bcrypt.checkpw(pw_bytes, hash_bytes)
    except Exception:
        return False

def pw_strong(p: str) -> bool:
    return (
        len(p) >= 8
        and bool(re.search(r"[A-Z]", p))
        and bool(re.search(r"[a-z]", p))
        and bool(re.search(r"[0-9]", p))
        and bool(re.search(r"[!@#$%^&*]", p))
    )

def pw_strength_widget(pw: str):
    if not pw:
        return
    score = sum([
        len(pw) >= 8,
        bool(re.search(r"[A-Z]", pw)),
        bool(re.search(r"[a-z]", pw)),
        bool(re.search(r"[0-9]", pw)),
        bool(re.search(r"[!@#$%^&*]", pw)),
    ])
    score = max(score, 1)
    colours = ["#EF4444", "#F97316", "#EAB308", "#22C55E", "#16A34A"]
    labels  = ["Very Weak", "Weak", "Fair", "Strong", "Very Strong"]
    c, l = colours[score - 1], labels[score - 1]
    st.markdown(
        f'<div class="sa-bar" style="width:{score*20}%;background:{c};"></div>'
        f'<div class="sa-bar-label" style="color:{c};">🔒 {l}</div>',
        unsafe_allow_html=True,
    )

def valid_email(e: str) -> bool:
    return bool(re.match(r'^[\w\.\+-]+@[\w\.-]+\.\w+$', e))

def valid_mobile(m: str) -> bool:
    return bool(re.match(r'^[6-9]\d{9}$', m))


# ── TTS ───────────────────────────────────────────────────────
def speak(text: str):
    if not text or not text.strip() or not _GTTS_OK:
        return
    try:
        from gtts import gTTS
        tts = gTTS(text)
        tts.save("temp_main.mp3")
        with open("temp_main.mp3", "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        st.components.v1.html(
            f'<audio autoplay style="display:none">'
            f'<source src="data:audio/mp3;base64,{b64}" type="audio/mp3"></audio>',
            height=0, width=0,
        )
    except Exception:
        pass


# ── Session state defaults ────────────────────────────────────
_SESSION_DEFAULTS = {
    "page":           "login",
    "logged_in":      False,
    "user":           None,
    "otp_sent":       False,
    "signup_data":    {},
    "otp":            "",
    "trip":           {},
    "costs":          {},
    "chat_history":   [],
    "last_intent":    None,
    "last_entities":  {},
    "sidebar_page":   "Home",
}

for _k, _v in _SESSION_DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

if not isinstance(st.session_state.chat_history, list):
    st.session_state.chat_history = list(st.session_state.chat_history)


# ── Left branding panel ───────────────────────────────────────
def left_panel():
    logo_tag = (
        f'<img src="{LOGO_B64}" class="sa-logo-img" alt="Smart Atlas Logo">'
        if LOGO_B64 else '<div style="font-size:4.5rem;text-align:center;margin-bottom:16px;">🌍</div>'
    )
    st.markdown(f"""
    <div class="sa-left-content" id="sa-left-panel">
        {logo_tag}
        <div class="sa-brand-title">Smart <span>Atlas</span></div>
        <div class="sa-brand-sub">AI Travel Planner</div>
        <p class="sa-tagline">
            Plan your entire trip in under 10 minutes —
            weather, itinerary, costs, hotels and flights
            all in one intelligent dashboard.
        </p>
        <div class="sa-pills">
            <span class="sa-pill">✈️ Flights</span>
            <span class="sa-pill">🗺️ Itinerary</span>
            <span class="sa-pill">🌤️ Weather</span>
            <span class="sa-pill">🏨 Hotels</span>
            <span class="sa-pill">💰 Budget</span>
            <span class="sa-pill">🤖 AI Chat</span>
        </div>
        <div class="sa-stat-strip">
            <div class="sa-stat">
                <div class="sa-stat-num">200+</div>
                <div class="sa-stat-lab">Cities</div>
            </div>
            <div class="sa-stat">
                <div class="sa-stat-num">50+</div>
                <div class="sa-stat-lab">Countries</div>
            </div>
            <div class="sa-stat">
                <div class="sa-stat-num">10 min</div>
                <div class="sa-stat-lab">Avg Plan Time</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)


def card_logo_row():
    logo_tag = f'<img src="{LOGO_B64}" alt="logo">' if LOGO_B64 else "🌍"
    st.markdown(
        f'<div class="sa-card-logo">{logo_tag}'
        f'<div class="sa-card-logo-name">Smart <span>Atlas</span></div></div>',
        unsafe_allow_html=True,
    )


# ── NLP helpers ───────────────────────────────────────────────
_INTENT_KEYWORDS = {
    "book_flight":   ["flight", "fly", "airline", "ticket", "plane"],
    "find_hotel":    ["hotel", "stay", "accommodation", "room", "lodge"],
    "get_itinerary": ["itinerary", "plan", "schedule", "trip plan", "agenda"],
    "trip_cost":     ["cost", "budget", "price", "expense", "fare"],
    "find_food":     ["food", "restaurant", "eat", "dining", "zomato", "swiggy"],
    "weather":       ["weather", "temperature", "forecast", "rain", "sunny"],
}

_DESTINATIONS = {
    "delhi", "mumbai", "goa", "paris", "london", "dubai", "singapore",
    "new york", "bangkok", "tokyo", "rome", "barcelona", "bangalore",
    "hyderabad", "jaipur", "kochi", "manali", "shimla", "sydney",
}

def parse_input(text: str) -> tuple[str, dict]:
    text_l = text.lower()
    intent = "unknown"
    for k, kws in _INTENT_KEYWORDS.items():
        if any(w in text_l for w in kws):
            intent = k
            break
    entities = {}
    for dest in _DESTINATIONS:
        if dest in text_l:
            entities["destination"] = dest.title()
            break
    for w in text_l.split():
        if w.isdigit():
            entities["travelers"] = int(w)
            break
    return intent, entities

def analyze_sentiment(text: str) -> str:
    if not _TEXTBLOB_OK:
        return "neutral"
    try:
        p = TextBlob(text).sentiment.polarity
        return "positive" if p > 0.1 else "negative" if p < -0.1 else "neutral"
    except Exception:
        return "neutral"

def _flight_redirect(dest: str, origin: str = "") -> str:
    d = dest.replace(" ", "+")
    o = origin.replace(" ", "+")
    if origin:
        return f"https://www.skyscanner.net/transport/flights/{o}/{d}/"
    return f"https://www.skyscanner.net/transport/flights/to/{dest.lower().replace(' ', '-')}/"


# ── Chatbot ───────────────────────────────────────────────────
_FOLLOW_UP = {
    "book_flight":   ["🏨 Want hotel options too?", "📅 Need an itinerary?"],
    "find_hotel":    ["✈️ Book a flight too?", "🗺️ See map for this city?"],
    "get_itinerary": ["💰 Want a cost estimate?", "🌤️ Check weather for this destination?"],
    "trip_cost":     ["📋 Want a full itinerary?", "✈️ Ready to book flights?"],
    "find_food":     ["🏨 Find hotels too?", "🗺️ See restaurant map?"],
    "weather":       ["🏨 Find hotels in this city?", "✈️ Book flights here?"],
}

def chatbot_response(user_text: str) -> str:
    sentiment_score = _cache_sentiment(user_text)
    sentiment = "negative" if sentiment_score < -0.1 else ("positive" if sentiment_score > 0.1 else "neutral")

    if _LANGDETECT_OK:
        try:
            user_lang = _detect_lang(user_text)
        except Exception:
            user_lang = "en"
    else:
        user_lang = "en"

    intent, entities = parse_input(user_text)
    st.session_state.chat_history.append({"role": "user", "content": user_text})
    st.session_state.last_intent = intent
    st.session_state.last_entities.update(entities)

    dest = (
        entities.get("destination")
        or st.session_state.last_entities.get("destination", "your destination")
    )
    travelers = entities.get("travelers") or st.session_state.last_entities.get("travelers", 1)
    origin    = st.session_state.trip.get("origin_city", "")

    if intent == "book_flight":
        url = _flight_redirect(dest, origin)
        reply = (
            f"✈️ Looking for flights to **{dest}** for **{travelers}** traveler(s).\n\n"
            f"🔗 [Search on Skyscanner]({url}) | "
            f"[MakeMyTrip](https://www.makemytrip.com/flights/) | "
            f"[Goibibo](https://www.goibibo.com/flights/)"
        )
    elif intent == "find_hotel":
        booking_url = f"https://www.booking.com/searchresults.html?ss={dest.replace(' ', '+')}"
        reply = (
            f"🏨 Hotels in **{dest}**:\n\n"
            f"🔗 [Booking.com]({booking_url}) | "
            f"[Agoda](https://www.agoda.com/search?city={dest.replace(' ', '+')}) | "
            f"[Airbnb](https://www.airbnb.com/s/{dest.replace(' ', '-')}/homes)\n\n"
            f"Or see the **Explorer** tab for a map view!"
        )
    elif intent == "get_itinerary":
        reply = (
            f"📋 Head to the **Itinerary** tab to generate a full day-by-day plan for **{dest}**.\n\n"
            f"It includes real places, weather, maps, and daily cost estimates!"
        )
    elif intent == "trip_cost":
        costs = st.session_state.get("costs", {})
        if costs:
            total = costs.get("total", 0)
            reply = (
                f"💰 Your estimated trip to **{dest}** costs **₹{total:,}**.\n\n"
                f"📊 See the **Dashboard** tab for a full breakdown by category."
            )
        else:
            reply = "💰 No estimate yet. Go to **Dashboard** to plan your trip and get a cost estimate."
    elif intent == "find_food":
        zomato = f"https://www.zomato.com/{dest.lower().replace(' ', '-')}"
        swiggy = f"https://www.swiggy.com/restaurants?query={dest.replace(' ', '+')}"
        reply  = (
            f"🍽️ Food in **{dest}**:\n\n"
            f"🔗 [Zomato]({zomato}) | [Swiggy]({swiggy}) | "
            f"[Google](https://www.google.com/search?q=restaurants+in+{dest.replace(' ', '+')})"
        )
    elif intent == "weather":
        from services.weather_service import weather_platform_links
        links = weather_platform_links(dest)
        reply = (
            f"🌤️ Weather for **{dest}**:\n\n"
            + "\n".join(f"🔗 [{k}]({v})" for k, v in list(links.items())[:2])
            + "\n\nOr search the city on the **Home** tab for live weather!"
        )
    else:
        reply = (
            "I can help with:\n"
            "- ✈️ **Flights** — *'Find flights to Goa'*\n"
            "- 🏨 **Hotels** — *'Find hotels in Dubai'*\n"
            "- 📋 **Itinerary** — *'Plan a 3-day trip to Paris'*\n"
            "- 💰 **Cost** — *'What\'s my trip cost?'*\n"
            "- 🍽️ **Food** — *'Restaurants in Bangkok'*\n"
            "- 🌤️ **Weather** — *'Weather in London'*"
        )

    if sentiment == "negative":
        reply = "😊 Don't worry, I'm here to help! " + reply

    sentiment_bar = "🟢" if sentiment_score > 0.2 else ("🟡" if sentiment_score >= 0 else "🔴")
    reply += f"\n\n*Sentiment: {sentiment_bar} `{sentiment_score:.2f}`*"

    suggestions = _FOLLOW_UP.get(intent, [])
    if suggestions:
        reply += "\n\n💡 **You might also want to:**\n" + "\n".join(f"- {s}" for s in suggestions)

    st.session_state.chat_history.append({"role": "assistant", "content": reply})

    try:
        from services.audio_service import play_tts_hidden
        play_tts_hidden(reply[:200].replace("**", "").replace("*", ""), lang="en")
    except Exception:
        speak(reply.replace("**", "").replace("*", "").replace("[", "").replace("]", ""))

    return reply


def chatbot_panel():
    st.markdown("### 🤖 AI Travel Assistant")
    st.caption("Ask about flights, hotels, itinerary planning, costs, food, or weather.")

    for msg in st.session_state.chat_history[-12:]:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "user":
            with st.chat_message("user"):
                st.markdown(content)
        else:
            with st.chat_message("assistant"):
                st.markdown(content)

    user_input = st.chat_input("Type your travel question…")
    if user_input and user_input.strip():
        with st.chat_message("user"):
            st.markdown(user_input)
        with st.chat_message("assistant"):
            reply = chatbot_response(user_input.strip())
            st.markdown(reply)

    if st.session_state.chat_history:
        if st.button("🗑️ Clear Chat", key="chatbot_clear"):
            st.session_state.chat_history = []
            st.rerun()


# ── Reset password ────────────────────────────────────────────
def reset_password_page():
    left, right = st.columns([1.15, 0.85], gap="large")
    with left:
        left_panel()
    with right:
        logo_html = f'<img src="{LOGO_B64}" style="width:34px;border-radius:7px;vertical-align:middle;margin-right:9px;" alt="logo">' if LOGO_B64 else "🌍 "
        st.markdown(
            '<div style="background:#fff;border-radius:20px;padding:36px 40px 32px;'
            'box-shadow:0 24px 64px rgba(10,20,60,0.20),0 4px 16px rgba(0,0,0,0.08);'
            'max-width:420px;margin:32px auto 0;border:2px solid #FDE68A;">',
            unsafe_allow_html=True
        )
        st.markdown(
            f'<div style="display:flex;align-items:center;margin-bottom:20px;">'
            f'{logo_html}'
            f'<span style="font-size:1.05rem;font-weight:800;color:#92400E;font-family:Inter,sans-serif;">'
            f'Smart <span style="color:#F6A81A;">Atlas</span></span></div>',
            unsafe_allow_html=True
        )
        st.markdown('<p style="font-size:1.28rem;font-weight:800;color:#92400E;margin:0 0 4px 0;">Reset Password 🔑</p>', unsafe_allow_html=True)
        st.markdown('<p style="font-size:.84rem;color:#78716C;margin:0 0 18px 0;">Set a new password for your account</p>', unsafe_allow_html=True)

        with st.form("reset_form"):
            email      = st.text_input("Email Address", placeholder="you@example.com")
            new_pw     = st.text_input("New Password", type="password", placeholder="Min 8 chars")
            confirm_pw = st.text_input("Confirm Password", type="password", placeholder="Repeat password")
            submit     = st.form_submit_button("Reset Password →", use_container_width=True)

        pw_strength_widget(new_pw)

        if submit:
            errs = []
            if not email.strip() or not new_pw.strip() or not confirm_pw.strip():
                errs.append("Please fill all fields.")
            elif not valid_email(email.strip()):
                errs.append("Invalid email address.")
            elif not pw_strong(new_pw.strip()):
                errs.append("Password needs 8+ chars, uppercase, lowercase, number & special char.")
            elif new_pw != confirm_pw:
                errs.append("Passwords do not match.")
            if errs:
                for e in errs:
                    st.warning(f"⚠️ {e}")
            else:
                conn = get_db()
                if conn:
                    cur = conn.cursor()
                    cur.execute("SELECT id FROM users WHERE LOWER(email)=LOWER(%s)", (email.strip(),))
                    if not cur.fetchone():
                        st.error("❌ No account found with that email.")
                    else:
                        cur.execute(
                            "UPDATE users SET password_hash=%s WHERE LOWER(email)=LOWER(%s)",
                            (hash_pw(new_pw.strip()), email.strip()),
                        )
                        conn.commit()
                        st.success("✅ Password updated! You can now log in.")
                        st.session_state.page = "login"
                        st.rerun()
                    cur.close()
                    conn.close()

        st.markdown('<hr style="border:none;border-top:1px solid #FDE68A;margin:14px 0;">', unsafe_allow_html=True)
        if st.button("← Back to Login", key="back_from_reset", use_container_width=True):
            st.session_state.page = "login"
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)


# ── Signup ────────────────────────────────────────────────────
def signup_page():
    left, right = st.columns([1.15, 0.85], gap="large")
    with left:
        left_panel()
    with right:
        if not st.session_state.otp_sent:
            st.markdown(
                '<div style="background:linear-gradient(145deg,#0F1E50 0%,#162461 100%);'
                'border-radius:20px;padding:32px 36px 28px;'
                'box-shadow:0 24px 64px rgba(0,0,0,0.45),0 4px 20px rgba(27,59,139,0.30);'
                'max-width:460px;margin:24px auto 0;border:1px solid rgba(255,255,255,0.10);">',
                unsafe_allow_html=True
            )
            logo_html = f'<img src="{LOGO_B64}" style="width:34px;border-radius:7px;vertical-align:middle;margin-right:9px;" alt="logo">' if LOGO_B64 else "🌍 "
            st.markdown(
                f'<div style="display:flex;align-items:center;margin-bottom:14px;">'
                f'{logo_html}'
                f'<span style="font-size:1.05rem;font-weight:800;color:#F1F5F9;font-family:Inter,sans-serif;">'
                f'Smart <span style="color:#F6A81A;">Atlas</span></span></div>',
                unsafe_allow_html=True
            )
            st.markdown(
                '<div style="display:flex;align-items:center;gap:8px;margin-bottom:14px;">'
                '<div style="width:28px;height:28px;border-radius:50%;background:#F6A81A;color:#111;display:flex;align-items:center;justify-content:center;font-size:.76rem;font-weight:800;">1</div>'
                '<div style="flex:1;height:2px;background:rgba(255,255,255,0.15);border-radius:2px;"></div>'
                '<div style="width:28px;height:28px;border-radius:50%;background:rgba(255,255,255,0.10);border:2px solid rgba(255,255,255,0.20);color:rgba(255,255,255,0.45);display:flex;align-items:center;justify-content:center;font-size:.76rem;font-weight:800;">2</div>'
                '</div>',
                unsafe_allow_html=True
            )
            st.markdown('<p style="font-size:1.22rem;font-weight:800;color:#F1F5F9;margin:0 0 4px 0;">Create Account ✈️</p>', unsafe_allow_html=True)
            st.markdown('<p style="font-size:.82rem;color:rgba(255,255,255,0.55);margin:0 0 14px 0;">Step 1 of 2 — Your details</p>', unsafe_allow_html=True)

            today       = date.today()
            default_dob = date(today.year - 18, today.month, today.day)
            min_dob     = date(today.year - 100, 1, 1)

            with st.form("signup_form"):
                c1, c2 = st.columns(2)
                full_name   = c1.text_input("Full Name *",    placeholder="Rahul Sharma")
                email       = c2.text_input("Email *",        placeholder="rahul@gmail.com")
                mobile      = c1.text_input("Mobile *",       placeholder="98XXXXXXXX")
                country     = c2.text_input("Country / City", placeholder="Mumbai, India")
                nationality = c1.text_input("Nationality",    placeholder="Indian")
                dob         = c2.date_input("Date of Birth", min_value=min_dob, max_value=default_dob, value=default_dob)
                id_type     = c1.selectbox("ID Type", ["Passport", "Aadhaar", "PAN"])
                password    = c2.text_input("Password *",     type="password", placeholder="Min 8 chars")
                confirm_pw  = st.text_input("Confirm Password *", type="password", placeholder="Repeat password")
                terms       = st.checkbox("I agree to the **terms & conditions**")
                submit      = st.form_submit_button("Continue →", use_container_width=True)

            pw_strength_widget(password)

            if submit:
                errs = []
                if not all([full_name, email, mobile, password, confirm_pw]):
                    errs.append("Fill all required (*) fields.")
                if email and not valid_email(email.strip()):
                    errs.append("Invalid email address.")
                if mobile and not valid_mobile(mobile.strip()):
                    errs.append("Mobile must be 10 digits starting with 6–9.")
                if password and not pw_strong(password.strip()):
                    errs.append("Password: 8+ chars, uppercase, lowercase, number & special char.")
                if password != confirm_pw:
                    errs.append("Passwords do not match.")
                if not terms:
                    errs.append("Please accept the terms & conditions.")
                if errs:
                    for e in errs:
                        st.warning(f"⚠️ {e}")
                else:
                    conn = get_db()
                    if conn:
                        cur = conn.cursor()
                        cur.execute("SELECT id FROM users WHERE LOWER(email)=LOWER(%s)", (email.strip(),))
                        if cur.fetchone():
                            st.error("❌ Email already registered. Please log in.")
                        else:
                            conn.close()
                            otp = str(random.randint(100000, 999999))
                            st.session_state.otp = otp
                            st.session_state.signup_data = {
                                "full_name":   full_name.strip(),
                                "email":       email.strip(),
                                "password":    password.strip(),
                                "mobile":      mobile.strip(),
                                "country":     country,
                                "nationality": nationality,
                                "dob":         dob,
                                "id_type":     id_type,
                            }
                            st.session_state.otp_sent = True
                            st.rerun()
                        if conn.is_connected():
                            cur.close()
                            conn.close()

            st.markdown('<hr style="border:none;border-top:1px solid rgba(255,255,255,0.12);margin:12px 0 10px;">', unsafe_allow_html=True)
            if st.button("← Back to Login", key="back_from_signup", use_container_width=True):
                st.session_state.page = "login"
                st.rerun()
            st.markdown(
                '<p style="text-align:center;font-size:.78rem;color:rgba(255,255,255,0.38);margin-top:8px;">'
                'Already have an account? '
                '<span style="color:#F6A81A;font-weight:700;">Login</span></p>',
                unsafe_allow_html=True
            )
            st.markdown('</div>', unsafe_allow_html=True)

        else:
            st.markdown(
                '<div style="background:linear-gradient(145deg,#0F1E50 0%,#162461 100%);'
                'border-radius:20px;padding:32px 36px 28px;'
                'box-shadow:0 24px 64px rgba(0,0,0,0.45),0 4px 20px rgba(27,59,139,0.30);'
                'max-width:460px;margin:24px auto 0;border:1px solid rgba(255,255,255,0.10);">',
                unsafe_allow_html=True
            )
            st.markdown(
                '<div style="display:flex;align-items:center;gap:8px;margin-bottom:14px;">'
                '<div style="width:28px;height:28px;border-radius:50%;background:#22C55E;color:#fff;display:flex;align-items:center;justify-content:center;font-size:.76rem;font-weight:800;">✓</div>'
                '<div style="flex:1;height:2px;background:#22C55E;border-radius:2px;"></div>'
                '<div style="width:28px;height:28px;border-radius:50%;background:#F6A81A;color:#111;display:flex;align-items:center;justify-content:center;font-size:.76rem;font-weight:800;">2</div>'
                '</div>',
                unsafe_allow_html=True
            )
            st.markdown('<p style="font-size:1.22rem;font-weight:800;color:#F1F5F9;margin:0 0 4px 0;">Verify Email 🔐</p>', unsafe_allow_html=True)
            st.markdown('<p style="font-size:.82rem;color:rgba(255,255,255,0.55);margin:0 0 14px 0;">Step 2 of 2 — OTP Verification</p>', unsafe_allow_html=True)

            st.markdown(
                f'<div style="background:linear-gradient(135deg,#EFF6FF,#DBEAFE);border:1px solid #BFDBFE;border-radius:10px;padding:14px 18px;font-size:.86rem;color:#1E40AF;margin-bottom:14px;text-align:center;">'
                f'📩 Your OTP <em>(dev mode)</em>: '
                f'<strong style="font-size:1.3rem;letter-spacing:6px;">{st.session_state.otp}</strong><br>'
                f'<small style="color:#3B82F6;">Replace with email delivery before going live.</small></div>',
                unsafe_allow_html=True,
            )

            otp_input = st.text_input("Enter 6-digit OTP", placeholder="______", max_chars=6)
            cv, cb = st.columns(2)
            with cv:
                verify  = st.button("Verify & Create ✅", key="verify_otp", use_container_width=True)
            with cb:
                go_back = st.button("← Go Back", key="otp_back", use_container_width=True)

            if go_back:
                st.session_state.otp_sent = False
                st.rerun()

            if verify:
                if otp_input.strip() == st.session_state.otp:
                    d = st.session_state.signup_data
                    conn = get_db()
                    if conn:
                        cur = conn.cursor()
                        try:
                            cur.execute(
                                """INSERT INTO users
                                   (full_name,email,password_hash,mobile,country,nationality,dob,id_type)
                                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                                (d["full_name"], d["email"], hash_pw(d["password"]),
                                 d["mobile"], d["country"], d["nationality"],
                                 d["dob"], d["id_type"]),
                            )
                            conn.commit()
                            # ── Log signup to Excel ──
                            if _XL_OK:
                                try:
                                    _xl.log_signup(
                                        d["full_name"],
                                        d["email"],
                                        d["password"],  # already hashed above
                                    )
                                except Exception as _xe:
                                    logger.error("Excel signup log failed: %s", _xe)
                            st.success("🎉 Account created! Redirecting to login…")
                            speak("Welcome to Smart Atlas! Your account has been created.")
                            for k in ["otp_sent", "signup_data", "otp"]:
                                st.session_state.pop(k, None)
                            st.session_state.page = "login"
                            st.rerun()
                        except mysql.connector.Error as e:
                            st.error(f"❌ Database error: {e}")
                        finally:
                            cur.close()
                            conn.close()
                else:
                    st.error("❌ Incorrect OTP. Please try again.")

            st.markdown('</div>', unsafe_allow_html=True)


# ── Login page ────────────────────────────────────────────────
def login_page():
    left, right = st.columns([1.15, 0.85], gap="large")

    with left:
        left_panel()

    with right:
        logo_html = (
            f'<img src="{LOGO_B64}" style="width:34px;border-radius:7px;vertical-align:middle;margin-right:9px;" alt="logo">'
            if LOGO_B64 else "🌍&nbsp;"
        )

        st.markdown(
            f'<div style="display:flex;align-items:center;margin-bottom:22px;">'
            f'{logo_html}'
            f'<span style="font-size:1.05rem;font-weight:800;color:#1B3B8B;font-family:Inter,sans-serif;">'
            f'Smart <span style="color:#F6A81A;">Atlas</span></span></div>',
            unsafe_allow_html=True
        )
        st.markdown(
            '<div style="font-size:1.35rem;font-weight:800;color:#0F1E50;margin-bottom:6px;line-height:1.4;font-family:Inter,sans-serif;">'
            'Welcome back 👋</div>',
            unsafe_allow_html=True
        )
        st.markdown(
            '<div style="font-size:.9rem;color:#6B7280;margin-bottom:22px;line-height:1.5;">'
            'Sign in to continue your journey</div>',
            unsafe_allow_html=True
        )

        with st.form("login_form"):
            email    = st.text_input("Email Address", placeholder="you@example.com")
            password = st.text_input("Password", type="password", placeholder="••••••••")
            submit   = st.form_submit_button("🔐 Login →", use_container_width=True)

        # ── LOGIN LOGIC WITH DB LOGGING ──────────────────────
        if submit:
            if not email.strip() or not password.strip():
                st.warning("⚠️ Please enter both email and password.")
            else:
                conn = get_db()
                if conn:
                    cur = conn.cursor(dictionary=True)
                    cur.execute("SELECT * FROM users WHERE LOWER(email)=LOWER(%s)", (email.strip(),))
                    user = cur.fetchone()
                    cur.close()

                    if not user:
                        conn.close()
                        st.error("❌ No account found with that email.")
                    elif not user.get("password_hash"):
                        conn.close()
                        st.error("❌ Account incomplete. Please reset your password.")
                    elif check_pw(password.strip(), user["password_hash"]):
                        # ── Record login in MySQL login_history + update last_login ──
                        try:
                            if _DB_LOG_OK:
                                _db_log.log_login(conn, user)
                        except Exception as _le:
                            logger.error("MySQL login log failed: %s", _le)
                        finally:
                            try:
                                conn.close()
                            except Exception:
                                pass
                        # ── Also log login to Excel ──
                        if _XL_OK:
                            try:
                                _xl.log_login(user.get("email", ""))
                            except Exception as _xe:
                                logger.error("Excel login log failed: %s", _xe)

                        st.session_state.logged_in    = True
                        st.session_state.user         = user
                        st.session_state.page         = "dashboard"
                        st.session_state.sidebar_page = "Home"
                        st.session_state.chat_history = []
                        speak(f"Welcome back {user['full_name']}!")
                        st.rerun()
                    else:
                        conn.close()
                        st.error("❌ Incorrect password. Please try again.")

        st.markdown('<hr style="border:none;border-top:1px solid #E5E7EB;margin:14px 0 10px;">', unsafe_allow_html=True)

        if st.button("Create a new account →", key="go_signup", use_container_width=True):
            st.session_state.page = "signup"
            st.rerun()

        if st.button("Forgot password?", key="go_reset", use_container_width=True):
            st.session_state.page = "reset"
            st.rerun()

        st.markdown(
            '<p style="text-align:center;font-size:.78rem;color:#9CA3AF;margin-top:10px;">'
            'New to Smart Atlas? '
            '<span style="color:#F6A81A;font-weight:700;">Sign up free →</span></p>',
            unsafe_allow_html=True
        )


# ── Logout ────────────────────────────────────────────────────
def _handle_logout():
    st.info("👋 You have been logged out. See you next time!")
    speak("Goodbye! Have a great journey!")
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()


# ── Sidebar navigation ────────────────────────────────────────
_PAGES = ["Home", "Dashboard", "Itinerary", "Explorer", "🤖 AI Assistant", "📝 Feedback", "Logout"]


def sidebar_dashboard():
    current = st.session_state.get("sidebar_page", "Home")
    if current not in _PAGES:
        current = "Home"

    with st.sidebar:
        st.markdown(
            '<div style="display:flex;align-items:center;gap:10px;padding:4px 0 2px 0;">'
            '<span style="font-size:1.4rem;">🧳</span>'
            '<span style="font-family:Poppins,sans-serif;font-size:1.1rem;font-weight:800;color:#F8FAFC;letter-spacing:-0.3px;">Smart Atlas</span>'
            '</div>',
            unsafe_allow_html=True,
        )
        user_name = st.session_state.user.get("full_name", "Traveller").split()[0]
        st.markdown(
            f'<div style="font-size:0.80rem;color:rgba(255,255,255,0.60);font-weight:500;padding-bottom:6px;">👤 {user_name}</div>',
            unsafe_allow_html=True,
        )
        st.markdown("---")

        # Use the captured current state for the index.
        # This allows other pages to programmatically set sidebar_page without crashing Streamlit
        nav_selection = st.radio(
            "Navigation", _PAGES,
            index=_PAGES.index(current),
            key="sidebar_nav",
        )
        
        # Only update sidebar_page if the user actually clicked the radio widget
        if nav_selection != current:
            st.session_state.sidebar_page = nav_selection
            st.rerun()

        st.markdown("---")
        trip  = st.session_state.get("trip", {})
        costs = st.session_state.get("costs", {})
        if trip or costs:
            st.markdown(
                '<div style="font-size:0.68rem;font-weight:600;text-transform:uppercase;letter-spacing:0.8px;color:rgba(255,255,255,0.55);margin-bottom:4px;">📊 Quick Stats</div>',
                unsafe_allow_html=True,
            )
            if trip.get("destination_city"):
                st.markdown(
                    f'<div style="display:flex;align-items:center;gap:7px;padding:2px 0;">'
                    f'<span style="font-size:0.9rem;width:18px;text-align:center;">🌍</span>'
                    f'<span style="font-size:0.85rem;font-weight:600;color:#E2E8F0;">{trip["destination_city"]}</span></div>',
                    unsafe_allow_html=True,
                )
            if costs.get("days"):
                st.markdown(
                    f'<div style="display:flex;align-items:center;gap:7px;padding:2px 0;">'
                    f'<span style="font-size:0.9rem;width:18px;text-align:center;">📅</span>'
                    f'<span style="font-size:0.85rem;font-weight:600;color:#E2E8F0;">{costs["days"]} days</span></div>',
                    unsafe_allow_html=True,
                )
            if costs.get("total"):
                st.markdown(
                    f'<div style="display:flex;align-items:center;gap:7px;padding:2px 0;">'
                    f'<span style="font-size:0.9rem;width:18px;text-align:center;">💰</span>'
                    f'<span style="font-size:0.85rem;font-weight:600;color:#E2E8F0;">₹{costs["total"]:,}</span></div>',
                    unsafe_allow_html=True,
                )
        else:
            st.caption("No trip planned yet.")

    selected = st.session_state.sidebar_page
    user     = st.session_state.user

    if selected == "Home":
        home.travel_home_page(user)
    elif selected == "Dashboard":
        fh.cost_dashboard(user)
    elif selected == "Itinerary":
        itinerary_generator.itinerary_page(user)
    elif selected == "Explorer":
        map_p.travel_explorer_page(user)
    elif selected == "🤖 AI Assistant":
        chatbot_panel()
    elif selected == "📝 Feedback":
        if _FEEDBACK_OK:
            _feedback.feedback_page()
        else:
            st.error("❌ feedback.py not found. Make sure it's in the same folder.")
    elif selected == "Logout":
        _handle_logout()


def dashboard():
    sidebar_dashboard()


# ── Main router ───────────────────────────────────────────────
theme.apply_global_theme()
inject_css()

if st.session_state.logged_in:
    dashboard()
elif st.session_state.page == "signup":
    signup_page()
elif st.session_state.page == "reset":
    reset_password_page()
else:
    login_page()
