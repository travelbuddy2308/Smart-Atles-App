# services/audio_service.py
# ============================================================
# Smart Atles — Audio / TTS & Language Service
# ✅ Multi-language TTS via gTTS
# ✅ Offline TTS fallback via pyttsx3
# ✅ Language auto-detect from text (langdetect)
# ✅ Local greeting phrases per city
# ✅ Background chime toggle (pydub)
# ✅ Session-level audio caching
# ✅ Volume normalization helpers
# ============================================================

import base64
import io
import logging
import os

import streamlit as st

logger = logging.getLogger(__name__)

# ── City → language code mapping ─────────────────────────────
_CITY_LANG = {
    # India
    "mumbai": "hi", "delhi": "hi", "bangalore": "hi", "hyderabad": "hi",
    "chennai": "ta", "kolkata": "bn", "ahmedabad": "gu", "kochi": "ml",
    "pune": "hi", "jaipur": "hi", "varanasi": "hi", "agra": "hi",
    "goa": "hi", "shimla": "hi", "manali": "hi",
    # International
    "paris": "fr", "marseille": "fr", "nice": "fr",
    "madrid": "es", "barcelona": "es",
    "tokyo": "ja", "osaka": "ja", "kyoto": "ja",
    "beijing": "zh", "shanghai": "zh",
    "rome": "it", "milan": "it", "venice": "it",
    "berlin": "de", "munich": "de",
    "moscow": "ru",
    "seoul": "ko",
    "dubai": "ar", "abu dhabi": "ar",
    "bangkok": "th",
    "lisbon": "pt", "rio de janeiro": "pt",
    "amsterdam": "nl",
    "athens": "el",
    "istanbul": "tr",
    "cairo": "ar",
    "singapore": "en",
    "london": "en", "sydney": "en", "new york": "en", "toronto": "en",
}

# ── Local greeting phrases ────────────────────────────────────
_LOCAL_PHRASES = {
    # India
    "mumbai":    ("Namaste", "नमस्ते — Welcome to Mumbai!"),
    "delhi":     ("Namaste", "नमस्ते — Welcome to Delhi!"),
    "bangalore": ("Namaskara", "ನಮಸ್ಕಾರ — Welcome to Bengaluru!"),
    "chennai":   ("Vanakkam", "வணக்கம் — Welcome to Chennai!"),
    "kolkata":   ("Namaskar", "নমস্কার — Welcome to Kolkata!"),
    "jaipur":    ("Khamma Ghani", "खम्मा घणी — Welcome to Jaipur!"),
    "varanasi":  ("Jai Shiv Shankar", "जय शिव शंकर — Welcome to Varanasi!"),
    "hyderabad": ("Namaste", "నమస్తే — Welcome to Hyderabad!"),
    "kochi":     ("Namaskaram", "നമസ്കാരം — Welcome to Kochi!"),
    "goa":       ("Dev Borem Karun", "Dev Borem Karun — Welcome to Goa!"),
    "ahmedabad": ("Kem Cho", "કેમ છો — Welcome to Ahmedabad!"),
    # International
    "paris":      ("Bonjour",   "Bonjour! — Welcome to Paris!"),
    "tokyo":      ("Konnichiwa", "こんにちは — Welcome to Tokyo!"),
    "osaka":      ("Konnichiwa", "こんにちは — Welcome to Osaka!"),
    "madrid":     ("Hola",       "¡Hola! — Welcome to Madrid!"),
    "barcelona":  ("Hola",       "¡Hola! — Welcome to Barcelona!"),
    "rome":       ("Ciao",       "Ciao! — Welcome to Rome!"),
    "berlin":     ("Hallo",      "Hallo! — Willkommen in Berlin!"),
    "dubai":      ("Marhaba",    "مرحباً — Welcome to Dubai!"),
    "bangkok":    ("Sawadee kha","สวัสดี — Welcome to Bangkok!"),
    "singapore":  ("Selamat Datang", "Selamat Datang — Welcome to Singapore!"),
    "amsterdam":  ("Hallo",      "Hallo! — Welkom in Amsterdam!"),
    "istanbul":   ("Merhaba",    "Merhaba! — Welcome to Istanbul!"),
    "seoul":      ("Annyeong",   "안녕하세요 — Welcome to Seoul!"),
    "moscow":     ("Privet",     "Привет — Welcome to Moscow!"),
    "cairo":      ("Ahlan wa Sahlan", "أهلاً وسهلاً — Welcome to Cairo!"),
    "athens":     ("Yassas",     "Γεια σας — Welcome to Athens!"),
    "lisbon":     ("Olá",        "Olá! — Bem-vindo a Lisboa!"),
}

# ── Language names for display ────────────────────────────────
_LANG_NAME = {
    "en": "English", "hi": "Hindi", "ta": "Tamil", "bn": "Bengali",
    "gu": "Gujarati", "ml": "Malayalam", "fr": "French", "es": "Spanish",
    "ja": "Japanese", "zh": "Chinese", "it": "Italian", "de": "German",
    "ru": "Russian", "ko": "Korean", "ar": "Arabic", "th": "Thai",
    "pt": "Portuguese", "nl": "Dutch", "el": "Greek", "tr": "Turkish",
}

# ── Audio cache directory ─────────────────────────────────────
_AUDIO_CACHE = {}  # in-memory session cache: text_hash → b64


def detect_language(text: str, fallback: str = "en") -> str:
    """Detect language of text using langdetect; returns lang code."""
    try:
        from langdetect import detect
        lang = detect(text)
        return lang if lang else fallback
    except Exception:
        return fallback


def get_city_language(city: str) -> str:
    """Return gTTS-compatible language code for a city."""
    return _CITY_LANG.get(city.lower().strip(), "en")


def get_local_phrase(city: str) -> tuple[str, str]:
    """
    Return (short_greeting, full_welcome_line) for a city.
    Example: ("Bonjour", "Bonjour! — Welcome to Paris!")
    Falls back to English if city not mapped.
    """
    return _LOCAL_PHRASES.get(city.lower().strip(), ("Welcome", f"Welcome to {city}!"))


def get_language_name(lang_code: str) -> str:
    """Return human-readable language name from code."""
    return _LANG_NAME.get(lang_code, lang_code.upper())


def _text_to_b64(text: str, lang: str = "en") -> str | None:
    """
    Convert text to base64-encoded MP3 using gTTS.
    Returns None on failure.
    """
    cache_key = f"{lang}:{hash(text)}"
    if cache_key in _AUDIO_CACHE:
        return _AUDIO_CACHE[cache_key]

    try:
        from gtts import gTTS
        tts = gTTS(text=text, lang=lang, slow=False)
        buf = io.BytesIO()
        tts.write_to_fp(buf)
        buf.seek(0)
        b64 = base64.b64encode(buf.read()).decode()
        _AUDIO_CACHE[cache_key] = b64
        return b64
    except Exception as e:
        logger.warning("gTTS failed (lang=%s): %s", lang, e)
        return None


def _offline_tts(text: str):
    """Fallback TTS using pyttsx3 (works offline, Windows/Linux)."""
    try:
        import pyttsx3
        engine = pyttsx3.init()
        engine.setProperty("rate", 160)
        engine.setProperty("volume", 0.9)
        engine.say(text)
        engine.runAndWait()
    except Exception as e:
        logger.warning("pyttsx3 TTS failed: %s", e)


def play_tts(text: str, lang: str = "en", autoplay: bool = True) -> bool:
    """
    Render an audio player in Streamlit for the given text.
    Returns True if successful, False otherwise.
    Falls back to pyttsx3 if gTTS fails.
    """
    if not text or not text.strip():
        return False

    b64 = _text_to_b64(text, lang)
    if b64:
        audio_html = (
            f'<audio {"autoplay" if autoplay else ""} controls style="width:100%;margin-top:4px;">'
            f'<source src="data:audio/mp3;base64,{b64}" type="audio/mp3">'
            f"</audio>"
        )
        st.markdown(audio_html, unsafe_allow_html=True)
        return True

    # Fallback to offline TTS (no browser audio)
    _offline_tts(text)
    return False


def play_tts_hidden(text: str, lang: str = "en") -> bool:
    """Play TTS silently (autoplay, no visible controls)."""
    if not text or not text.strip():
        return False
    b64 = _text_to_b64(text, lang)
    if b64:
        st.markdown(
            f'<audio autoplay hidden>'
            f'<source src="data:audio/mp3;base64,{b64}" type="audio/mp3">'
            f"</audio>",
            unsafe_allow_html=True,
        )
        return True
    return False


def play_welcome_greeting(city: str):
    """
    Show the local greeting phrase for a city and play it via TTS.
    E.g., for Paris: "Bonjour! — Welcome to Paris!" in French.
    """
    greeting, full_line = get_local_phrase(city)
    lang = get_city_language(city)
    lang_name = get_language_name(lang)

    st.markdown(
        f'<div style="background:rgba(246,168,26,0.12);border-left:4px solid #F6A81A;'
        f'border-radius:0 10px 10px 0;padding:10px 16px;margin:8px 0;">'
        f'<span style="font-size:1.1rem;font-weight:700;color:#F6A81A;">{greeting}!</span> '
        f'<span style="color:#e2e8f0;">{full_line}</span> '
        f'<span style="font-size:0.8rem;color:rgba(255,255,255,0.5);">({lang_name})</span>'
        f"</div>",
        unsafe_allow_html=True,
    )
    play_tts_hidden(full_line, lang=lang)


def play_day_chime(day_number: int, city: str, travel_type: str = "Budget"):
    """
    Play a brief day-start narration for an itinerary day.
    E.g., "Day 1 in Paris. Bonjour!"
    Language auto-detected from city.
    """
    greeting, _ = get_local_phrase(city)
    lang = get_city_language(city)
    text = f"Day {day_number} in {city}. {greeting}! Here is your {travel_type} plan."
    play_tts_hidden(text, lang=lang)


def narrate_itinerary_day(day_number: int, city: str, places: list[str],
                           lang: str = "en", autoplay: bool = True) -> bool:
    """
    Generate and play audio narration for one itinerary day.
    Places is a list of place names.
    """
    if not places:
        return False
    places_text = ", ".join(places[:5])
    text = (
        f"Day {day_number} in {city}. "
        f"You will visit: {places_text}. "
        f"Have a wonderful day!"
    )
    return play_tts(text, lang=lang, autoplay=autoplay)


def render_music_toggle() -> bool:
    """
    Render a toggle in the sidebar to enable/disable background music.
    Returns True if music is enabled.
    """
    if "bg_music_enabled" not in st.session_state:
        st.session_state.bg_music_enabled = False

    enabled = st.sidebar.toggle(
        "🎵 Background Music",
        value=st.session_state.bg_music_enabled,
        key="bg_music_toggle",
        help="Enable soft background music while planning your trip",
    )
    st.session_state.bg_music_enabled = enabled
    return enabled


def mix_audio_files(speech_path: str, music_path: str, output_path: str,
                    music_volume_db: float = -18.0) -> str | None:
    """
    Mix a TTS speech file with background music using pydub.
    Returns output_path on success, None on failure.

    Args:
        speech_path:     Path to TTS MP3 file
        music_path:      Path to background music MP3 file
        output_path:     Where to save the mixed output MP3
        music_volume_db: Reduce music by this many dB (negative = quieter)
    """
    try:
        from pydub import AudioSegment
        speech = AudioSegment.from_mp3(speech_path)
        music  = AudioSegment.from_mp3(music_path)

        # Loop or trim music to match speech length
        while len(music) < len(speech):
            music = music + music
        music = music[: len(speech)]

        # Lower music volume
        music = music + music_volume_db

        # Overlay
        combined = speech.overlay(music)
        combined.export(output_path, format="mp3")
        return output_path
    except Exception as e:
        logger.warning("Audio mix failed: %s", e)
        return None


def play_chime_from_file(chime_path: str):
    """
    Play a chime/music file from disk in Streamlit (autoplay hidden).
    The file must be in assets/audio/ and under ~200KB for performance.
    """
    if not os.path.exists(chime_path):
        logger.debug("Chime file not found: %s", chime_path)
        return
    try:
        with open(chime_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        st.markdown(
            f'<audio autoplay hidden><source src="data:audio/mp3;base64,{b64}" '
            f'type="audio/mp3"></audio>',
            unsafe_allow_html=True,
        )
    except Exception as e:
        logger.warning("Failed to play chime %s: %s", chime_path, e)


def tts_widget(label: str = "🔊 Listen", key_prefix: str = "tts") -> None:
    """
    Render a small TTS input widget: user types or confirms text,
    then clicks Listen to hear it spoken.
    Useful for chatbot or weather description readout.
    """
    col1, col2 = st.columns([4, 1])
    with col1:
        text = st.text_input("Text to speak:", key=f"{key_prefix}_input", label_visibility="collapsed")
    with col2:
        if st.button(label, key=f"{key_prefix}_btn", use_container_width=True):
            if text:
                lang = detect_language(text)
                play_tts(text, lang=lang, autoplay=True)
            else:
                st.warning("Enter text to speak.")
