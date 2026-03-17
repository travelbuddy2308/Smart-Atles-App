# home.py
# ============================================================
# Smart Atlas — Home Page
# Live weather · Interactive map · Itinerary preview
# Smart chatbot · Platform redirect links (Aggregator model)
# ============================================================

import streamlit as st
import requests
import folium
import base64
from streamlit_folium import st_folium

try:
    import db_logger as _db_log
    _DB_LOG_OK = True
except ImportError:
    _DB_LOG_OK = False

# ── Audio / language service (fail-safe) ─────────────────────
try:
    from services.audio_service import (
        play_tts_hidden, detect_language, get_city_language,
        get_local_phrase, get_language_name,
    )
    _AUDIO_OK = True
except Exception:
    _AUDIO_OK = False
    def play_tts_hidden(text, lang="en"): pass
    def detect_language(text, fallback="en"): return fallback
    def get_city_language(city): return "en"
    def get_local_phrase(city): return ("Welcome", f"Welcome to {city}!")
    def get_language_name(code): return "English"

# ── Constants ─────────────────────────────────────────────────
_DEFAULT_CITY   = "Paris"
_DEFAULT_COORDS = (48.8566, 2.3522)
_WEATHER_URL    = "https://api.openweathermap.org/data/2.5/weather"

_WEATHER_EMOJI = {
    "clear": "☀️", "cloud": "☁️", "rain": "🌧️", "drizzle": "🌦️",
    "thunderstorm": "⛈️", "snow": "❄️", "mist": "🌫️",
    "haze": "🌫️", "fog": "🌫️", "smoke": "💨", "dust": "💨",
}

# ── Platform redirect helpers (Aggregator Model) ──────────────
def _flight_url(city: str) -> str:
    return f"https://www.skyscanner.net/transport/flights/to/{city.replace(' ', '-').lower()}/"

def _hotel_url(city: str) -> str:
    return f"https://www.booking.com/searchresults.html?ss={city.replace(' ', '+')}"

def _food_url(city: str) -> str:
    return f"https://www.zomato.com/{city.lower().replace(' ', '-')}"

def _weather_url(city: str) -> str:
    return f"https://www.accuweather.com/en/search-locations?query={city.replace(' ', '+')}"

def _maps_url(lat: float, lon: float, city: str = "") -> str:
    q = city.replace(" ", "+") if city else f"{lat},{lon}"
    return f"https://www.google.com/maps/search/{q}/@{lat},{lon},13z"


# ── TTS helper ────────────────────────────────────────────────
def speak(text: str):
    if not text or not text.strip():
        return
    try:
        from gtts import gTTS
        tts = gTTS(text)
        tts.save("temp_home.mp3")
        with open("temp_home.mp3", "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        st.components.v1.html(
            f'<audio autoplay style="display:none">'
            f'<source src="data:audio/mp3;base64,{b64}" type="audio/mp3"></audio>',
            height=0,
        )
    except Exception:
        pass


# ── Weather fetch ─────────────────────────────────────────────
def _get_weather_key() -> str:
    try:
        k = st.secrets.get("OPENWEATHER_API_KEY", "")
        if not k:
            k = st.secrets.get("api", {}).get("openweather_key", "")
        return k
    except Exception:
        return ""

def fetch_weather(city: str) -> bool:
    api_key = _get_weather_key()
    if not api_key:
        st.warning("⚠️ Weather API key not configured in `.streamlit/secrets.toml`.")
        return False
    try:
        resp = requests.get(
            _WEATHER_URL,
            params={"q": city.strip(), "units": "metric", "appid": api_key},
            timeout=8,
        )
        if resp.status_code == 404:
            st.error(f"🔍 City **'{city}'** not found. Check spelling and try again.")
            return False
        resp.raise_for_status()
        data = resp.json()
        st.session_state.weather_data   = {"city": city, "data": data}
        st.session_state.current_coords = (data["coord"]["lat"], data["coord"]["lon"])
        st.session_state.current_city   = city.title()
        return True
    except requests.exceptions.Timeout:
        st.error("⏱️ Request timed out. Check your internet connection.")
    except requests.exceptions.RequestException as e:
        st.error(f"⚠️ Could not fetch weather: {e}")
    return False

def _weather_emoji(desc: str) -> str:
    d = desc.lower()
    for kw, em in _WEATHER_EMOJI.items():
        if kw in d:
            return em
    return "🌡️"

def _weather_advice(temp: float, desc: str, humidity: int) -> tuple[str, str]:
    d = desc.lower()
    if "rain" in d or "thunder" in d:
        return "warning", "☔ Rainy — carry an umbrella and waterproof gear."
    elif "snow" in d:
        return "warning", "❄️ Snowy — pack warm layers and waterproof boots."
    elif temp > 35:
        return "warning", "🔥 Very hot — stay hydrated; use SPF 50+ sunscreen."
    elif temp < 5:
        return "warning", "🧥 Cold — heavy winter clothing required."
    elif humidity > 85:
        return "info", "💧 High humidity — breathable fabrics recommended."
    return "success", "✅ Great travel weather! Enjoy your trip."


# ── Chatbot ───────────────────────────────────────────────────
def _get_sentiment_score(text: str) -> str:
    """Return formatted sentiment score line using TextBlob (optional)."""
    try:
        from textblob import TextBlob
        score = TextBlob(text).sentiment.polarity
        bar   = "🟢" if score > 0.2 else ("🟡" if score >= 0 else "🔴")
        return f"\n\n*Sentiment: {bar} `{score:.2f}`*"
    except Exception:
        return ""


def _chatbot_reply(msg: str) -> str:
    msg_l  = msg.lower().strip()
    city   = st.session_state.get("current_city", _DEFAULT_CITY)
    trip   = st.session_state.get("trip", {})
    costs  = st.session_state.get("costs", {})
    dest   = trip.get("destination_city", city)
    wdata  = st.session_state.get("weather_data")

    # Detect user language and respond accordingly
    user_lang = detect_language(msg) if _AUDIO_OK else "en"
    lang_name = get_language_name(user_lang) if _AUDIO_OK else "English"

    # Greetings
    if any(w in msg_l for w in ["hi", "hello", "hey", "namaste", "good morning", "good evening"]):
        return (
            f"👋 Hello! I'm your Smart Atlas assistant. "
            f"You're viewing **{city}** right now. "
            "Ask me about weather, flights, hotels, costs, or itinerary!"
        )

    # Weather
    if any(w in msg_l for w in ["weather", "temperature", "forecast", "rain", "sunny", "cold"]):
        if wdata:
            d     = wdata["data"]
            cond  = d["weather"][0]["description"].title()
            temp  = d["main"]["temp"]
            hum   = d["main"]["humidity"]
            emoji = _weather_emoji(cond)
            return (
                f"{emoji} **{city} Weather:** {cond} | 🌡️ {temp}°C | 💧 {hum}% humidity\n\n"
                f"🔗 [Full Forecast on AccuWeather]({_weather_url(city)})"
            )
        return f"🔍 No weather data yet. Search a city above to get live weather."

    # Cost / budget
    if any(w in msg_l for w in ["cost", "budget", "price", "how much", "expense"]):
        if costs:
            total = costs.get("total", 0)
            return (
                f"💰 Your estimated trip to **{dest}** costs **₹{total:,}**.\n\n"
                f"📊 See the **Dashboard** tab for a full breakdown."
            )
        return "💰 No cost estimate yet. Go to **Dashboard** to plan your trip."

    # Itinerary
    if any(w in msg_l for w in ["itinerary", "plan", "schedule", "agenda", "day by day"]):
        return (
            f"📋 Your itinerary for **{dest}** is available in the **Itinerary** tab.\n\n"
            f"Head there to see your day-by-day plan with maps!"
        )

    # Hotels
    if any(w in msg_l for w in ["hotel", "stay", "accommodation", "lodge", "room"]):
        booking = _hotel_url(dest)
        return (
            f"🏨 Looking for hotels in **{dest}**?\n\n"
            f"🔗 [Booking.com]({booking}) | "
            f"[Agoda](https://www.agoda.com/search?city={dest.replace(' ', '+')}) | "
            f"[Airbnb](https://www.airbnb.com/s/{dest.replace(' ', '-')}/homes)\n\n"
            f"Or head to the **Explorer** tab for a map view!"
        )

    # Flights
    if any(w in msg_l for w in ["flight", "fly", "airline", "ticket", "plane"]):
        origin = trip.get("origin_city", "your city")
        skyscanner = f"https://www.skyscanner.net/transport/flights/{origin.replace(' ', '-')}/{dest.replace(' ', '-')}/"
        mmtrip = f"https://www.makemytrip.com/flights/"
        return (
            f"✈️ Flights from **{origin}** to **{dest}**:\n\n"
            f"🔗 [Skyscanner]({skyscanner}) | [MakeMyTrip]({mmtrip}) | "
            f"[Goibibo](https://www.goibibo.com/flights/) | [Kayak](https://www.kayak.com/flights)\n\n"
            f"Click any platform to see live prices and book!"
        )

    # Food
    if any(w in msg_l for w in ["food", "eat", "restaurant", "dining", "cuisine", "zomato", "swiggy"]):
        zomato = _food_url(dest)
        swiggy = f"https://www.swiggy.com/restaurants?query={dest.replace(' ', '+')}"
        return (
            f"🍽️ Restaurants in **{dest}**:\n\n"
            f"🔗 [Zomato]({zomato}) | [Swiggy]({swiggy}) | "
            f"[Google Food](https://www.google.com/search?q=restaurants+in+{dest.replace(' ', '+')})\n\n"
            f"Or check the **Explorer** tab for a restaurant map!"
        )

    # Help
    if any(w in msg_l for w in ["help", "what can", "options", "commands", "?"]):
        return (
            "I can help with:\n"
            "- 🌤️ **Weather** — *'What's the weather in Goa?'*\n"
            "- 💰 **Trip cost** — *'What is my trip cost?'*\n"
            "- 📋 **Itinerary** — *'Show my itinerary'*\n"
            "- ✈️ **Flights** — *'Find flights to Dubai'*\n"
            "- 🏨 **Hotels** — *'Find hotels in London'*\n"
            "- 🍽️ **Food** — *'Restaurants in Goa'*"
        )

    return (
        "🤔 I didn't catch that. Try asking:\n"
        "- *'What's the weather in Tokyo?'*\n"
        "- *'Find hotels in Goa'*\n"
        "- *'What's my trip cost?'*\n"
        "- *'Show my itinerary'*"
    )


# ── CSS ─────────────────────────────────────────────────────
def _inject_css():
    st.markdown("""
    <style>
    /* ── HOME PAGE SPECIFIC ───────────────────────── */
    /* Scroll fix */
    [data-testid="stAppViewContainer"] { overflow-y:auto !important; }
    .block-container { padding:1.8rem 1.6rem 5rem !important; max-width:1180px !important; }

    /* Home glassmorphism cards */
    .home-card {
        background:rgba(255,255,255,0.04);
        backdrop-filter:blur(18px); -webkit-backdrop-filter:blur(18px);
        border:1px solid rgba(255,255,255,0.08);
        border-radius:16px; padding:16px 18px; margin-bottom:12px;
        box-shadow:0 8px 32px rgba(31,38,135,0.07);
        transition:border-color .18s, box-shadow .18s;
    }
    .home-card:hover {
        border-color:rgba(245,158,11,0.18);
        box-shadow:0 10px 36px rgba(31,38,135,0.12);
    }

    /* Search input override for home */
    .stTextInput input,
    div[data-baseweb="input"] input {
        background:#0A1628 !important;
        border:1.5px solid rgba(148,163,184,0.18) !important;
        border-radius:10px !important;
        color:#E2E8F0 !important; caret-color:#F59E0B !important;
        -webkit-text-fill-color:#E2E8F0 !important;
        padding:10px 14px !important; font-size:0.90rem !important;
        font-family:'DM Sans',sans-serif !important;
        transition:border-color .18s, box-shadow .18s !important;
    }
    .stTextInput input::placeholder { color:rgba(148,163,184,0.32) !important; -webkit-text-fill-color:rgba(148,163,184,0.32) !important; }
    .stTextInput input:focus, div[data-baseweb="input"] input:focus {
        border-color:#F59E0B !important;
        box-shadow:0 0 0 3px rgba(245,158,11,0.14) !important;
        background:#0D1E3A !important;
    }
    div[data-baseweb="input"] { background:#0A1628 !important; border-radius:10px !important; }

    /* Section label */
    .sa-section-label {
        font-size:0.60rem; font-weight:700; text-transform:uppercase;
        letter-spacing:1.3px; color:rgba(148,163,184,0.42);
        margin:12px 0 5px 0; display:block;
        font-family:'DM Sans',sans-serif;
    }

    /* Search button */
    .stButton > button {
        background:linear-gradient(135deg,#F59E0B 0%,#D97706 100%) !important;
        color:#ffffff !important; border:none !important;
        border-radius:10px !important; padding:10px 18px !important;
        font-weight:800 !important; font-size:0.9rem !important;
        text-shadow: 0 1px 2px rgba(0,0,0,0.5);
        transition:transform .13s,box-shadow .13s !important;
        box-shadow:0 3px 14px rgba(245,158,11,0.32) !important;
    }
    .stButton > button:hover { transform:translateY(-2px) !important; box-shadow:0 7px 22px rgba(245,158,11,0.46) !important; }
    .stButton > button:active { transform:translateY(0) !important; }

    /* Link buttons */
    [data-testid="stLinkButton"] a {
        background:rgba(255,255,255,0.1) !important;
        border:1px solid rgba(255,255,255,0.2) !important;
        border-radius:9px !important; color:#ffffff !important;
        text-shadow: 0 1px 2px rgba(0,0,0,0.5);
        font-size:0.85rem !important; font-weight:700 !important;
        padding:7px 12px !important; text-decoration:none !important;
        display:inline-flex !important; align-items:center !important; gap:5px !important;
        transition:all .13s !important;
    }
    [data-testid="stLinkButton"] a:hover {
        background:rgba(245,158,11,0.12) !important;
        border-color:rgba(245,158,11,0.38) !important; color:#FCD34D !important;
    }

    /* Chat bubbles */
    .chat-container {
        background:rgba(0,0,0,0.25); border:1px solid rgba(255,255,255,0.1);
        border-radius:16px; padding:15px; max-height:300px; overflow-y:auto;
        margin-bottom:12px;
        box-shadow: inset 0 2px 10px rgba(0,0,0,0.2);
    }
    .chat-row-user { text-align:right; margin:6px 0; }
    .chat-row-bot  { text-align:left;  margin:6px 0; }
    .chat-user-bubble {
        background:linear-gradient(135deg,#F59E0B,#D97706); color:#0A0500;
        padding:10px 14px; border-radius:16px 16px 4px 16px;
        display:inline-block; max-width:85%; text-align:left;
        font-size:0.85rem; font-weight:500; font-family:'Inter',sans-serif;
        box-shadow: 0 4px 10px rgba(245,158,11,0.2);
    }
    .chat-bot-bubble {
        background:rgba(255,255,255,0.12); color:#F1F5F9;
        backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px);
        padding:10px 14px; border-radius:16px 16px 16px 4px;
        display:inline-block; max-width:85%;
        font-size:0.85rem; border:1px solid rgba(255,255,255,0.15);
        font-family:'Inter',sans-serif;
        box-shadow: 0 4px 10px rgba(0,0,0,0.1);
    }

    /* Tables */
    table { border-collapse:collapse; width:100%; }
    th { background:rgba(245,158,11,0.16) !important; color:#F1F5F9 !important;
         font-size:.76rem !important; padding:6px 10px !important;
         font-family:'DM Sans',sans-serif !important; font-weight:700 !important;
         text-transform:uppercase !important; letter-spacing:.5px !important; }
    td { color:#CBD5E1 !important; font-size:.82rem !important;
         padding:5px 10px !important;
         border-bottom:1px solid rgba(255,255,255,0.06) !important; }

    /* Metrics */
    [data-testid="stMetricLabel"] { color:rgba(148,163,184,0.65) !important; font-size:.68rem !important; font-weight:600 !important; text-transform:uppercase !important; letter-spacing:.6px !important; }
    [data-testid="stMetricValue"] { color:#F1F5F9 !important; font-size:1.22rem !important; font-weight:800 !important; font-family:'Syne',sans-serif !important; }
    </style>
    """, unsafe_allow_html=True)

def travel_home_page(user: dict):
    try:
        import theme
        theme.apply_global_theme()
    except ImportError:
        pass
    _inject_css()

    # Session defaults
    for k, v in [
        ("current_city",   _DEFAULT_CITY),
        ("current_coords", _DEFAULT_COORDS),
        ("weather_data",   None),
        ("chat_history",   []),
        ("trip",           {}),
        ("costs",          {}),
    ]:
        if k not in st.session_state:
            st.session_state[k] = v

    # Ensure chat_history is always a plain list
    if not isinstance(st.session_state.chat_history, list):
        st.session_state.chat_history = list(st.session_state.chat_history)

    # ── Header ─────────────────────────────────────────────
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:10px;padding:4px 0 14px 0;border-bottom:1px solid rgba(255,255,255,0.07);margin-bottom:16px;">' +
        f'<span style="font-size:1.5rem;">🏠</span>' +
        f'<div style="flex:1;">' +
        f'<div style="font-family:Syne,sans-serif;font-size:1.45rem;font-weight:800;color:#F1F5F9;letter-spacing:-0.4px;line-height:1;">Welcome, {user.get("full_name","Traveller")} ✈️</div>' +
        f'<div style="font-size:0.76rem;color:rgba(148,163,184,0.65);margin-top:2px;">Live Weather · Interactive Map · Smart Chatbot · Platform Links</div>' +
        f'</div>' +
        f'<span style="display:inline-flex;align-items:center;gap:4px;background:rgba(245,158,11,0.12);border:1px solid rgba(245,158,11,0.28);border-radius:100px;padding:3px 10px;font-size:0.72rem;font-weight:600;color:#FCD34D;font-family:DM Sans,sans-serif;">🌍 Home</span>' +
        '</div>',
        unsafe_allow_html=True,
    )

    # ── City search ─────────────────────────────────────────
    st.markdown('<div class="home-card">', unsafe_allow_html=True)
    st.markdown("#### 🔍 Search a City")
    col_s, col_b = st.columns([5, 1])
    with col_s:
        city_input = st.text_input(
            "City", value=st.session_state.current_city,
            placeholder="e.g. Tokyo, Goa, London",
            label_visibility="collapsed", key="home_city_input",
        )
    with col_b:
        searched = st.button("Search 🔍", key="home_search_btn", use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

    if searched and city_input.strip():
        # ── Log destination search ──
        if _DB_LOG_OK and st.session_state.get("user"):
            try:
                from log_p import get_db
                _lc = get_db()
                if _lc:
                    _db_log.log_search(_lc, st.session_state.user, city_input.strip(), "home")
                    _lc.close()
            except Exception:
                pass
        with st.spinner(f"Fetching data for **{city_input.strip()}**..."):
            if fetch_weather(city_input.strip()):
                st.success(f"✅ Showing data for **{city_input.strip().title()}**")

    if not st.session_state.weather_data:
        with st.spinner(f"Loading weather for {_DEFAULT_CITY}..."):
            fetch_weather(_DEFAULT_CITY)

    # ── Weather + Map + Itinerary preview ──────────────────
    if st.session_state.weather_data:
        wdata  = st.session_state.weather_data["data"]
        city   = st.session_state.current_city
        lat, lon = st.session_state.current_coords
        main   = wdata["main"]
        wind   = wdata["wind"]
        desc   = wdata["weather"][0]["description"].title()
        emoji  = _weather_emoji(desc)

        col1, col2, col3 = st.columns([1, 1.4, 1])

        # Weather card
        with col1:
            st.markdown('<div class="home-card">', unsafe_allow_html=True)
            st.markdown(f"#### 🌤️ Weather — {city}")
            st.markdown(f"**{emoji} {desc}**")
            st.metric("🌡️ Temperature", f"{main['temp']}°C", f"Feels {main['feels_like']}°C")
            st.metric("💧 Humidity", f"{main['humidity']}%")
            st.metric("💨 Wind", f"{wind.get('speed',0)} m/s")

            adv_type, adv_text = _weather_advice(main["temp"], desc, main["humidity"])
            if adv_type == "warning":
                st.warning(adv_text)
            elif adv_type == "success":
                st.success(adv_text)
            else:
                st.info(adv_text)

            st.link_button(
                "📡 Full Forecast", _weather_url(city), use_container_width=True
            )
            st.markdown('</div>', unsafe_allow_html=True)

        # Map card
        with col2:
            st.markdown('<div class="home-card">', unsafe_allow_html=True)
            st.markdown("#### 🗺️ Interactive Map")
            m = folium.Map(location=[lat, lon], zoom_start=11, tiles="CartoDB positron")
            folium.Marker(
                [lat, lon],
                popup=folium.Popup(
                    f"<b>{city}</b><br>{desc} | {main['temp']}°C", max_width=180
                ),
                tooltip=f"📍 {city}",
                icon=folium.Icon(color="blue", icon="plane", prefix="fa"),
            ).add_to(m)
            st_folium(m, width="100%", height=290)
            st.link_button(
                "🗺️ Open in Google Maps",
                _maps_url(lat, lon, city),
                use_container_width=True,
            )
            st.markdown('</div>', unsafe_allow_html=True)

        # Itinerary preview
        with col3:
            st.markdown('<div class="home-card">', unsafe_allow_html=True)
            st.markdown("#### 📋 Itinerary Preview")
            trip = st.session_state.get("trip", {})
            dest = trip.get("destination_city", city)
            days = int(trip.get("days", 4))
            if trip:
                for i in range(min(days, 4)):
                    st.markdown(f"**Day {i+1}:** Explore {dest}.")
                if days > 4:
                    st.caption(f"...and {days - 4} more days.")
            else:
                for i in range(4):
                    st.markdown(f"**Day {i+1}:** Explore {city}.")
                st.info("💡 Plan a trip on Dashboard to personalise.")
            if st.button("📋 Full Itinerary", key="home_itin_btn", use_container_width=True):
                st.session_state.sidebar_page = "Itinerary"
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

    # ── Quick platform links ─────────────────────────────────
    st.markdown('<div style="margin-top:8px;margin-bottom:4px;"><span style="font-size:0.72rem;font-weight:700;text-transform:uppercase;letter-spacing:0.8px;color:rgba(255,255,255,0.55);">🔗 Quick Booking Links</span></div>', unsafe_allow_html=True)
    city_now = st.session_state.get("current_city", _DEFAULT_CITY)
    qcols = st.columns(4)
    with qcols[0]:
        st.link_button("✈️ Flights (Skyscanner)", _flight_url(city_now), use_container_width=True)
    with qcols[1]:
        st.link_button("🏨 Hotels (Booking.com)", _hotel_url(city_now), use_container_width=True)
    with qcols[2]:
        st.link_button("🍽️ Restaurants (Zomato)", _food_url(city_now), use_container_width=True)
    with qcols[3]:
        st.link_button("📡 Weather Forecast", _weather_url(city_now), use_container_width=True)

    # ── Trip summary ─────────────────────────────────────────
    st.markdown('<div style="margin-top:8px;margin-bottom:4px;"><span style="font-size:0.72rem;font-weight:700;text-transform:uppercase;letter-spacing:0.8px;color:rgba(255,255,255,0.55);">🧾 Trip Summary</span></div>', unsafe_allow_html=True)
    trip  = st.session_state.trip
    costs = st.session_state.costs

    if trip:
        if trip.get("origin_city", "").lower() == trip.get("destination_city", "").lower():
            st.warning("⚠️ Origin and destination are the same. Update in Dashboard.")

        st.success("✅ Trip planned — here's your summary:")
        st.markdown('<div class="home-card">', unsafe_allow_html=True)
        st.table({
            "Field": ["Country", "Destination", "Days", "Travelers", "Travel Type"],
            "Value": [
                trip.get("dest_country", trip.get("country", "—")),
                trip.get("destination_city", "—"),
                str(trip.get("days", costs.get("days", "—"))),
                str(trip.get("travelers", "—")),
                trip.get("budget", trip.get("travel_type", "—")),
            ],
        })
        if costs:
            c1, c2, c3 = st.columns(3)
            c1.metric("💰 Total", f"₹{costs.get('total', 0):,}")
            c2.metric("👤 Per Person", f"₹{costs.get('per_person', 0):,}")
            c3.metric("📆 Per Day", f"₹{costs.get('per_day', 0):,}")
        st.markdown('</div>', unsafe_allow_html=True)

        ca, cb = st.columns(2)
        with ca:
            if st.button("📊 Full Dashboard", key="home_go_dash", use_container_width=True):
                st.session_state.sidebar_page = "Dashboard"
                st.rerun()
        with cb:
            if st.button("🗺️ Explore Destination", key="home_go_explore", use_container_width=True):
                st.session_state.sidebar_page = "Explorer"
                st.rerun()
    else:
        st.markdown('<div class="home-card">', unsafe_allow_html=True)
        st.info("No trip planned yet. Go to **Dashboard** to plan your first trip!")
        st.markdown('</div>', unsafe_allow_html=True)
        if st.button("🗺️ Plan a Trip Now", key="home_plan_now", use_container_width=True):
            st.session_state.sidebar_page = "Dashboard"
            st.rerun()

    # ── Smart Chatbot ────────────────────────────────────────
    st.markdown('<div style="margin-top:8px;margin-bottom:4px;"><span style="font-size:0.72rem;font-weight:700;text-transform:uppercase;letter-spacing:0.8px;color:rgba(255,255,255,0.55);">🤖 Travel Assistant</span></div>', unsafe_allow_html=True)

    # Language info
    city_now = st.session_state.get("current_city", _DEFAULT_CITY)
    if _AUDIO_OK:
        city_lang_code = get_city_language(city_now)
        lang_label     = get_language_name(city_lang_code)
        st.caption(
            f"Ask in any language · Detected city language: **{lang_label}** · "
            f"TTS responds in city's language"
        )
    else:
        st.caption("Ask about weather, flights, hotels, costs, food, or itinerary.")

    # Quick suggestion buttons
    st.markdown("**💡 Quick Suggestions:**")
    scols = st.columns(5)
    suggestions = [
        ("🌤️ Weather",  "What's the weather?"),
        ("✈️ Flights",  "Find me flights"),
        ("🏨 Hotels",   "Find hotels nearby"),
        ("💰 Cost",     "What is my trip cost?"),
        ("📋 Itinerary","Show my itinerary"),
    ]
    for i, (label, query) in enumerate(suggestions):
        with scols[i]:
            if st.button(label, key=f"home_qs_{i}", use_container_width=True):
                reply = _chatbot_reply(query)
                sentiment_suffix = _get_sentiment_score(query)
                st.session_state.chat_history.append({"msg": query, "role": "user"})
                st.session_state.chat_history.append({"msg": reply + sentiment_suffix, "role": "bot"})
                if _AUDIO_OK:
                    play_tts_hidden(reply[:200].replace("**", "").replace("*", ""), lang="en")
                else:
                    speak(reply.replace("**", "").replace("*", ""))
                st.rerun()

    # Chat history display
    history = st.session_state.chat_history[-10:]
    if history:
        chat_html = '<div class="chat-container">'
        for item in history:
            if item.get("role") == "user":
                chat_html += f'<div class="chat-row-user"><span class="chat-user-bubble">🧑 {item["msg"]}</span></div>'
            else:
                # Escape for inline HTML display (basic)
                chat_html += f'<div class="chat-row-bot"><span class="chat-bot-bubble">🤖 {item["msg"][:300]}</span></div>'
        chat_html += '</div>'
        st.markdown(chat_html, unsafe_allow_html=True)
    else:
        st.caption("No messages yet — start chatting! 👇")

    # Chat input
    ci, cs = st.columns([5, 1])
    with ci:
        user_msg = st.text_input(
            "Message", key="home_chat_input",
            placeholder="e.g. What's the weather in Tokyo?",
            label_visibility="collapsed",
        )
    with cs:
        send = st.button("Send ➤", key="home_send_chat", use_container_width=True)

    if send and user_msg.strip():
        reply            = _chatbot_reply(user_msg.strip())
        sentiment_suffix = _get_sentiment_score(user_msg.strip())
        full_reply       = reply + sentiment_suffix
        st.session_state.chat_history.append({"msg": user_msg.strip(), "role": "user"})
        st.session_state.chat_history.append({"msg": full_reply, "role": "bot"})
        # Language-aware TTS response
        if _AUDIO_OK:
            user_lang_code = detect_language(user_msg.strip())
            play_tts_hidden(reply[:250].replace("**", "").replace("*", ""), lang=user_lang_code)
        else:
            speak(reply.replace("**", "").replace("*", ""))
        st.rerun()

    if st.session_state.chat_history:
        if st.button("🗑️ Clear Chat", key="home_clear_chat"):
            st.session_state.chat_history = []
            st.rerun()

    pass
