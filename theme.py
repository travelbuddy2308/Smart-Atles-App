import streamlit as st
import base64
import os

# ─────────────────────────────────────────────
# NOIR THEME CONSTANTS (Lovable-Inspired)
# ─────────────────────────────────────────────

NOIR_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@200;300;400;500;600;700;800;900&display=swap');
@import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200');

:root {
    --background: #1A1A1A;
    --surface: #262626;
    --border: #333333;
    --primary: #ffffff;
    --text: #ffffff;
    --text-muted: #aaaaaa;
    --accent: #6366f1;
    --gold: #F6A81A;
}

* {
    font-family: 'Inter', sans-serif !important;
    box-sizing: border-box;
    -webkit-font-smoothing: antialiased;
}

/* Global Streamlit Overrides */
.stApp {
    background-color: var(--background) !important;
    color: var(--text) !important;
}

.main .block-container {
    padding-top: 3rem !important; /* Increased to prevent text overlap */
    padding-bottom: 3rem !important;
    max-width: 100% !important;
}

#MainMenu, footer, header {
    display: none !important;
}

/* Redesigned Navbar */
.nav-container {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    height: 80px;
    background: rgba(26, 26, 26, 0.8);
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    border-bottom: 1px solid rgba(255,255,255,0.05);
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 8%;
    z-index: 1000;
}

.brand {
    font-size: 1.1rem;
    font-weight: 700;
    letter-spacing: -0.02em;
    color: #fff;
    display: flex;
    align-items: center;
    gap: 10px;
}

.brand-icon {
    width: 20px;
    height: 20px;
    background: var(--gold);
    clip-path: polygon(50% 0%, 100% 50%, 50% 100%, 0% 50%);
}

.nav-links {
    display: flex;
    gap: 40px;
    align-items: center;
}

.nav-link {
    color: rgba(255,255,255,0.7);
    text-decoration: none;
    font-size: 0.85rem;
    font-weight: 500;
    transition: color 0.2s ease;
}

.nav-link:hover {
    color: #fff;
}

.get-access-btn {
    background: linear-gradient(135deg,#F59E0B 0%,#D97706 100%) !important;
    color: #ffffff !important;
    border: none !important;
    padding: 10px 20px !important;
    border-radius: 8px !important;
    font-size: 0.9rem !important;
    font-weight: 800 !important;
    text-shadow: 0 1px 2px rgba(0,0,0,0.5);
    text-decoration: none !important;
    transition: all 0.2s ease !important;
    box-shadow: 0 4px 12px rgba(245,158,11,0.3) !important;
}

.get-access-btn:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 16px rgba(245,158,11,0.4) !important;
}

/* Redesigned Hero */
.hero-section {
    padding: 180px 8% 120px;
    text-align: left;
    min-height: 90vh;
    display: flex;
    flex-direction: column;
    justify-content: center;
    position: relative;
    overflow: hidden;
}

.hero-sub {
    font-size: 0.75rem;
    font-weight: 700;
    color: var(--gold);
    text-transform: uppercase;
    letter-spacing: 0.3em;
    margin-bottom: 24px;
}

.hero-title {
    font-size: 6.5rem !important;
    font-weight: 800 !important;
    line-height: 0.9 !important;
    letter-spacing: -0.04em !important;
    margin-bottom: 32px !important;
    color: #fff !important;
}

.hero-title span {
    color: var(--gold);
}

.hero-tagline {
    font-size: 1.25rem !important;
    color: rgba(255,255,255,0.6) !important;
    max-width: 550px !important;
    line-height: 1.6 !important;
    margin-bottom: 48px !important;
}

.hero-btns {
    display: flex;
    gap: 20px;
}

/* Sections */
.content-section {
    padding: 120px 8%;
}

.section-label {
    font-size: 0.7rem;
    font-weight: 800;
    color: var(--gold);
    text-transform: uppercase;
    letter-spacing: 0.25em;
    margin-bottom: 20px;
}

.section-title {
    font-size: 3rem !important;
    font-weight: 800 !important;
    letter-spacing: -0.03em !important;
    margin-bottom: 60px !important;
    line-height: 1.1 !important;
}

/* Product Cards */
.feature-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 32px;
}

.feature-card {
    background: #262626;
    border: 1px solid #333;
    border-radius: 16px;
    padding: 48px 40px;
    transition: all 0.3s ease;
}

.feature-card:hover {
    border-color: #333;
    transform: translateY(-5px);
}

.feature-icon {
    font-size: 1.5rem;
    color: var(--gold);
    margin-bottom: 32px;
}

.feature-name {
    font-size: 1.35rem;
    font-weight: 700;
    margin-bottom: 16px;
    color: #fff;
}

.feature-desc {
    font-size: 1rem;
    color: rgba(255,255,255,0.5);
    line-height: 1.6;
}

/* Final CTA */
.final-cta {
    padding: 160px 8%;
    text-align: center;
    background: radial-gradient(circle at center, #262626 0%, #1A1A1A 70%);
}

.cta-title {
    font-size: 4rem !important;
    font-weight: 800 !important;
    letter-spacing: -0.04em !important;
    margin-bottom: 40px !important;
}

.cta-text {
    font-size: 1.1rem;
    color: rgba(255,255,255,0.5);
    max-width: 600px;
    margin: 0 auto 48px;
    line-height: 1.7;
}

/* Footer */
.footer {
    padding: 40px 8%;
    border-top: 1px solid #111;
    display: flex;
    justify-content: space-between;
    align-items: center;
    color: #444;
    font-size: 0.8rem;
}

/* Base Card - Flexible for grids and dashboards */
.sa-card {
    background: rgba(38, 38, 38, 0.4) !important;
    border: 1px solid rgba(255, 255, 255, 0.08) !important;
    backdrop-filter: blur(20px) !important;
    -webkit-backdrop-filter: blur(20px) !important;
    border-radius: 24px !important;
    padding: 32px !important;
    width: 100%;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    box-shadow: 0 4px 24px -1px rgba(0, 0, 0, 0.2);
}

.sa-card:hover {
    background: rgba(45, 45, 45, 0.5) !important;
    border-color: rgba(255, 255, 255, 0.15) !important;
    transform: translateY(-2px);
    box-shadow: 0 12px 40px -4px rgba(0, 0, 0, 0.3);
}

/* Fix for Material Icon text glitch */
.material-symbols-outlined {
    font-family: 'Material Symbols Outlined' !important;
}

/* Fix sidebar toggle text glitch */
[data-testid="stSidebar"] button[kind="secondary"] {
    color: transparent !important;
    position: relative;
}
[data-testid="stSidebar"] button[kind="secondary"]::after {
    content: 'unfold_more'; /* fallback icon */
    font-family: 'Material Symbols Outlined';
    color: var(--text);
    position: absolute;
    left: 50%;
    top: 50%;
    transform: translate(-50%, -50%);
    font-size: 20px;
    visibility: visible;
}

/* Auth Card - Specifically for Login/Signup centering */
.auth-card {
    background: rgba(38, 38, 38, 0.6) !important;
    border: 1px solid rgba(255,255,255,0.05) !important;
    backdrop-filter: blur(24px) !important;
    border-radius: 24px !important;
    padding: 44px !important;
    width: 100%;
    max-width: 480px;
    margin: 0 auto;
    box-shadow: 0 40px 100px rgba(0,0,0,0.6) !important;
    animation: slideUp 0.6s cubic-bezier(0.16, 1, 0.3, 1) both;
}

@keyframes slideUp {
    from { opacity: 0; transform: translateY(20px); }
    to { opacity: 1; transform: translateY(0); }
}

</style>
"""

def apply_global_theme():
    """Applies the main Noir theme used across all pages."""
    st.markdown(NOIR_CSS, unsafe_allow_html=True)
    
    # Inject the global background gradient and mountain image
    bg_b64 = _img_to_b64("asset/dark_mountain.png")
    if bg_b64:
        st.markdown(f"""
        <style>
        .stApp {{
            background: linear-gradient(rgba(0,0,0,0.4), rgba(0,0,0,0.6)), url("{bg_b64}") !important;
            background-size: cover !important;
            background-position: center !important;
            background-attachment: fixed !important;
        }}
        </style>
        """, unsafe_allow_html=True)

def _img_to_b64(path: str) -> str:
    try:
        if not os.path.exists(path):
            return ""
        with open(path, "rb") as f:
            data = base64.b64encode(f.read()).decode()
        ext = path.rsplit(".", 1)[-1].lower()
        mime = "jpeg" if ext in ("jpg", "jpeg") else ext
        return f"data:image/{mime};base64,{data}"
    except Exception:
        return ""

def speak(text: str):
    """Global utility for auto speech without player UI."""
    if not text or not text.strip():
        return
    try:
        from gtts import gTTS
        tts = gTTS(text)
        tts.save("temp.mp3")
        with open("temp.mp3", "rb") as f:
            b64_audio = base64.b64encode(f.read()).decode()
        st.components.v1.html(
            f'<audio autoplay style="display:none">'
            f'<source src="data:audio/mp3;base64,{b64_audio}" type="audio/mp3"></audio>',
            height=0,
        )
    except Exception:
        pass
