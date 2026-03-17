# itinerary_generator.py
# ============================================================
# Smart Atlas — Travel Itinerary Generator v2.1
# ✅ All original features preserved
# ✅ Auto-sort attractions by proximity (haversine)
# ✅ Highlight top 3 attractions per day (gold badge)
# ✅ Optional Skip Day feature per day
# ✅ Activity tags: Family-friendly / Couples / Solo
# ✅ Average time per place shown on schedule
# ✅ Daily itinerary notifications via st.toast
# ✅ Color-coded schedule items (food/sightseeing/hotel)
# ✅ Day-based packing advice from weather
# ✅ Toggle map tile styles (Street/Dark/Terrain/etc.)
# ✅ Local public transport stations on map
# ✅ Local greeting phrases + language-aware TTS
# ✅ Background music toggle
# ✅ Itinerary NLP auto-summary
# ✅ Cost estimation caching per session
# ✅ Pre-filter and deduplicate places before rendering
# ============================================================

import streamlit as st
from streamlit_folium import st_folium
from datetime import datetime, timedelta
import folium
import io
import base64
import logging

logger = logging.getLogger(__name__)

try:
    import db_logger as _db_log
    _DB_LOG_OK = True
except ImportError:
    _DB_LOG_OK = False

try:
    import excel_logger as _xl
    _XL_OK = True
except ImportError:
    _XL_OK = False

try:
    import theme
except Exception:
    theme = None

from services.weather_service import get_weather_by_city
from services.places_service  import get_places_for_city
from services.hotel_service   import get_hotels_near, get_platform_links as hotel_platform_links
from services.food_service    import get_food_near, get_platform_links as food_platform_links

# ── New service imports (all fail-safe) ───────────────────────
try:
    from services.audio_service import (
        play_welcome_greeting, play_day_chime, narrate_itinerary_day,
        render_music_toggle, get_city_language, get_local_phrase,
        play_tts_hidden,
    )
    _AUDIO_OK = True
except Exception:
    _AUDIO_OK = False
    def play_welcome_greeting(city): pass
    def play_day_chime(n, city, travel_type="Budget"): pass
    def narrate_itinerary_day(n, city, places, lang="en", autoplay=True): return False
    def render_music_toggle(): return False
    def get_city_language(city): return "en"
    def get_local_phrase(city): return ("Welcome", f"Welcome to {city}!")
    def play_tts_hidden(text, lang="en"): pass

try:
    from services.map_service import (
        sort_by_proximity, get_top_attractions,
        fetch_transport_stops_osm, generate_day_map as _gen_map_service,
        TILE_STYLES,
    )
    _MAP_SERVICE_OK = True
except Exception:
    _MAP_SERVICE_OK = False
    TILE_STYLES = {"Street": {"label": "🗺️ Street"}}
    def sort_by_proximity(places, lat, lon): return places
    def get_top_attractions(places, n=3): return places[:n]
    def fetch_transport_stops_osm(lat, lon, radius_m=800): return []

# ── Location data ─────────────────────────────────────────────
LOCATION_DATA = {
    "India": {
        "Andhra Pradesh":    ["Vishakhapatnam", "Vijayawada", "Guntur", "Tirupati"],
        "Arunachal Pradesh": ["Itanagar", "Tawang", "Ziro"],
        "Assam":             ["Guwahati", "Dibrugarh", "Silchar"],
        "Bihar":             ["Patna", "Gaya", "Bhagalpur"],
        "Chhattisgarh":      ["Raipur", "Bilaspur"],
        "Goa":               ["Panaji", "Margao", "Vasco da Gama"],
        "Gujarat":           ["Ahmedabad", "Surat", "Vadodara", "Rajkot"],
        "Haryana":           ["Gurgaon", "Faridabad", "Panipat"],
        "Himachal Pradesh":  ["Shimla", "Manali", "Dharamshala", "Solan"],
        "Jharkhand":         ["Ranchi", "Jamshedpur"],
        "Karnataka":         ["Bangalore", "Mysore", "Mangalore", "Hubli"],
        "Kerala":            ["Kochi", "Thiruvananthapuram", "Kozhikode", "Alappuzha"],
        "Madhya Pradesh":    ["Bhopal", "Indore", "Gwalior", "Ujjain"],
        "Maharashtra":       ["Mumbai", "Pune", "Nagpur", "Nashik"],
        "Manipur":           ["Imphal"],
        "Meghalaya":         ["Shillong", "Tura"],
        "Mizoram":           ["Aizawl"],
        "Nagaland":          ["Kohima", "Dimapur"],
        "Odisha":            ["Bhubaneswar", "Puri", "Cuttack"],
        "Punjab":            ["Amritsar", "Chandigarh", "Ludhiana"],
        "Rajasthan":         ["Jaipur", "Udaipur", "Jodhpur", "Ajmer"],
        "Sikkim":            ["Gangtok", "Pelling"],
        "Tamil Nadu":        ["Chennai", "Coimbatore", "Madurai", "Tiruchirapalli"],
        "Telangana":         ["Hyderabad", "Warangal"],
        "Tripura":           ["Agartala"],
        "Uttar Pradesh":     ["Lucknow", "Agra", "Varanasi", "Kanpur"],
        "Uttarakhand":       ["Dehradun", "Haridwar", "Nainital", "Rishikesh"],
        "West Bengal":       ["Kolkata", "Darjeeling", "Siliguri"],
        "Delhi":             ["New Delhi", "Dwarka", "Rohini"],
    },
    "USA": {
        "New York":    ["New York City"],
        "California":  ["Los Angeles", "San Francisco", "San Diego"],
        "Illinois":    ["Chicago"],
        "Florida":     ["Miami", "Orlando"],
        "Nevada":      ["Las Vegas"],
    },
    "UK": {
        "England":  ["London", "Manchester", "Birmingham"],
        "Scotland": ["Edinburgh", "Glasgow"],
    },
    "France": {
        "Île-de-France": ["Paris"],
        "Provence":      ["Marseille", "Nice"],
    },
    "UAE": {
        "Dubai":     ["Dubai"],
        "Abu Dhabi": ["Abu Dhabi"],
    },
    "Singapore": {
        "Central Region": ["Singapore"],
    },
    "Thailand": {
        "Bangkok":    ["Bangkok"],
        "Phuket":     ["Phuket"],
        "Chiang Mai": ["Chiang Mai"],
    },
    "Japan": {
        "Kanto":  ["Tokyo", "Yokohama"],
        "Kansai": ["Osaka", "Kyoto", "Nara"],
    },
    "Australia": {
        "New South Wales": ["Sydney"],
        "Victoria":        ["Melbourne"],
        "Queensland":      ["Brisbane", "Gold Coast"],
    },
    "Germany": {
        "Bavaria":  ["Munich"],
        "Berlin":   ["Berlin"],
    },
    "Italy": {
        "Lazio":   ["Rome"],
        "Veneto":  ["Venice"],
        "Lombardy":["Milan"],
    },
}

# ── Cost profiles ─────────────────────────────────────────────
COST_PROFILES = {
    "India": {
        "hotel":      {"Budget": 1200,  "Luxury": 5000},
        "meal":       {"Breakfast": 150, "Lunch": 250, "Dinner": 300},
        "transport":  {"Cab": 300, "Metro": 60, "Auto": 50},
        "activity":   {"Sightseeing": 150},
        "misc":       75,
    },
    "_default": {
        "hotel":      {"Budget": 6000,  "Luxury": 20000},
        "meal":       {"Breakfast": 800, "Lunch": 1500, "Dinner": 2000},
        "transport":  {"Cab": 1500, "Metro": 300, "Auto": 200, "Car": 2000, "Walking": 0},
        "activity":   {"Sightseeing": 1000},
        "misc":       300,
    },
}


# ── Activity tag presets ──────────────────────────────────────
ACTIVITY_TAGS = {
    "👨‍👩‍👧 Family": ["museum", "park", "beach", "zoo", "theme park", "aquarium"],
    "💑 Couples":  ["sunset", "garden", "fort", "lake", "palace", "rooftop"],
    "🧳 Solo":     ["cafe", "market", "temple", "gallery", "trail", "bookshop"],
    "🏃 Adventure":["trek", "rafting", "skydiving", "bungee", "camping", "waterfall"],
    "🎭 Cultural": ["museum", "heritage", "temple", "church", "mosque", "ruins"],
}

# ── Average visit duration by place keyword ───────────────────
_DURATION_MAP = {
    "museum": 90, "fort": 90, "palace": 75, "temple": 45, "church": 40,
    "mosque": 40, "beach": 120, "park": 60, "garden": 50, "lake": 45,
    "market": 60, "zoo": 120, "cafe": 30, "gallery": 60, "trail": 150,
    "waterfall": 60, "falls": 60, "cave": 75, "monument": 45, "ruins": 60,
}


def _estimate_duration(place_name: str) -> int:
    """Estimate visit duration (minutes) from place name keywords."""
    name_lower = place_name.lower()
    for keyword, minutes in _DURATION_MAP.items():
        if keyword in name_lower:
            return minutes
    return 60


def _assign_tags(place_name: str) -> list:
    """Return matching activity tags for a place based on name keywords."""
    name_lower = place_name.lower()
    tags = []
    for tag, keywords in ACTIVITY_TAGS.items():
        if any(kw in name_lower for kw in keywords):
            tags.append(tag)
    return tags[:3]


def _dedup_places(places: list) -> list:
    """Deduplicate places list by name (case-insensitive)."""
    seen = set()
    result = []
    for p in places:
        key = p["name"].lower().strip()
        if key not in seen:
            seen.add(key)
            result.append(p)
    return result


def _summarize_itinerary_nlp(city: str, days: int, places_all: list) -> str:
    """Generate a short NLP summary with optional TextBlob sentiment score."""
    place_names = ", ".join([p["name"] for p in places_all[:8]])
    base_text = (
        f"A {days}-day trip to {city} covering highlights like {place_names}. "
        f"This itinerary offers a great mix of culture, sightseeing, and local experiences."
    )
    try:
        from textblob import TextBlob
        blob = TextBlob(base_text)
        sentiment = blob.sentiment.polarity
        mood = "🌟 Excellent" if sentiment > 0.3 else ("😐 Moderate" if sentiment > 0 else "🔍 Review needed")
        return f"{base_text}\n\n**AI Sentiment Score:** `{sentiment:.2f}` — {mood}"
    except Exception:
        return base_text


def outfit_and_pack(temp: float, condition: str) -> dict:
    suggestions, accessories, packlist = [], [], []
    cond = condition.lower()

    if "rain" in cond or "drizzle" in cond or "thunderstorm" in cond:
        suggestions.append("Wet conditions expected — wear waterproof clothing.")
        accessories += ["Umbrella", "Raincoat", "Waterproof bag cover"]
        packlist    += ["Extra socks", "Plastic pouches", "Towel"]
    elif "snow" in cond:
        suggestions.append("Snowy — wear warm waterproof layers.")
        accessories += ["Wool cap", "Gloves", "Scarf", "Snow boots"]
        packlist    += ["Thermals", "Warm socks", "Hand warmers"]
    elif temp >= 35:
        suggestions.append("Very hot — light breathable cotton; stay hydrated.")
        accessories += ["Sunglasses", "Cap/Hat"]
        packlist    += ["Sunscreen SPF 50+", "Water bottle", "Electrolytes"]
    elif temp >= 25:
        suggestions.append("Warm — casual breathable clothing works well.")
        accessories += ["Sunglasses"]
        packlist    += ["Sunscreen", "Water bottle"]
    elif temp < 5:
        suggestions.append("Very cold — heavy winter gear essential.")
        accessories += ["Wool cap", "Gloves", "Thick scarf"]
        packlist    += ["Heavy jacket", "Thermals", "Woollen socks"]
    elif temp < 15:
        suggestions.append("Cool — layered clothing recommended.")
        accessories += ["Light scarf"]
        packlist    += ["Light jacket", "Full sleeves", "Comfortable shoes"]
    else:
        suggestions.append("Pleasant weather — comfortable layered clothing.")
        accessories += ["Light jacket for evenings"]
        packlist    += ["Comfortable shoes", "Light scarf"]

    return {
        "summary":     " ".join(suggestions),
        "accessories": list(set(accessories)),
        "packlist":    list(set(packlist)),
    }


# ── Daily cost calculator ─────────────────────────────────────
def calculate_daily_cost(country: str, travel_type: str,
                          places_count: int, transport: str) -> dict:
    profile    = COST_PROFILES.get(country, COST_PROFILES["_default"])
    multiplier = 1 if travel_type == "Budget" else 3

    hotel          = profile["hotel"].get(travel_type, profile["hotel"]["Budget"])
    meal           = sum(profile["meal"].values()) * multiplier
    transport_rate = profile["transport"].get(transport,
                     profile["transport"].get("Cab", 300))
    transport_cost = max(places_count, 1) * transport_rate * multiplier
    activity       = max(places_count, 1) * profile["activity"]["Sightseeing"] * multiplier
    misc           = profile["misc"] * multiplier
    total          = hotel + meal + transport_cost + activity + misc

    return {
        "🏨 Hotel":     hotel,
        "🍽️ Meals":    meal,
        "🚗 Transport": transport_cost,
        "🎯 Activity":  activity,
        "📦 Misc":      misc,
        "total":        total,
    }


# ── Map builder ───────────────────────────────────────────────
def _build_map(places: list, hotels: list, foods: list) -> folium.Map:
    if not places:
        return folium.Map(location=[20.5937, 78.9629], zoom_start=5, tiles="CartoDB positron")

    m = folium.Map(location=[places[0]["lat"], places[0]["lon"]], zoom_start=13, tiles="CartoDB positron")

    for p in places:
        folium.Marker(
            [p["lat"], p["lon"]], tooltip=p["name"],
            popup=folium.Popup(f"<b>🏛️ {p['name']}</b>", max_width=180),
            icon=folium.Icon(color="green", icon="star", prefix="fa"),
        ).add_to(m)

    for h in hotels:
        booking_link = h.get("booking_url", "")
        popup_html = (
            f"<b>🏨 {h['name']}</b><br>"
            f"<a href='{booking_link}' target='_blank'>Book on Booking.com</a>"
            if booking_link else f"<b>🏨 {h['name']}</b>"
        )
        folium.Marker(
            [h["lat"], h["lon"]], tooltip=f"🏨 {h['name']}",
            popup=folium.Popup(popup_html, max_width=200),
            icon=folium.Icon(color="blue", icon="bed", prefix="fa"),
        ).add_to(m)

    for f in foods:
        zomato_link = f.get("zomato_url", "")
        popup_html = (
            f"<b>🍽️ {f['name']}</b><br>"
            f"<a href='{zomato_link}' target='_blank'>View on Zomato</a>"
            if zomato_link else f"<b>🍽️ {f['name']}</b>"
        )
        folium.Marker(
            [f["lat"], f["lon"]], tooltip=f"🍽️ {f['name']}",
            popup=folium.Popup(popup_html, max_width=200),
            icon=folium.Icon(color="red", icon="cutlery", prefix="fa"),
        ).add_to(m)

    return m


# ── Safety tips ───────────────────────────────────────────────
def _safety_tips():
    with st.expander("⚠️ Safety Tips & Important Notes", expanded=False):
        st.markdown("""
- 🪪 Carry government ID and a photocopy
- 📞 Save emergency contacts locally (no internet needed)
- 💧 Stay hydrated; carry a refillable water bottle
- 👗 Respect local dress codes at religious sites
- 🚕 Use official/licensed transport providers only
- 💵 Carry small cash; ATMs may not be available everywhere
- 🔋 Pack a power bank and basic first-aid kit
- 📷 Check photography rules before shooting at monuments
- 🛂 Ensure visa/travel documents are valid well beyond trip dates
        """)


# ── CSS ─────────────────────────────────────────────────────
def _inject_css():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Syne:wght@600;700;800&family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700;1,9..40,400&display=swap');
    [data-testid="stAppViewContainer"] { overflow-y:auto !important; }
    .block-container { padding:1.8rem 1.6rem 5rem !important; max-width:1180px !important; }

    /* Itinerary day card */
    .itin-card {
        background:rgba(255,255,255,0.04);
        backdrop-filter:blur(16px); -webkit-backdrop-filter:blur(16px);
        border:1px solid rgba(255,255,255,0.07);
        border-radius:14px; padding:14px 16px; margin-bottom:10px;
        box-shadow:0 4px 20px rgba(0,0,0,0.20);
        transition:border-color .15s;
    }
    .itin-card:hover { border-color:rgba(245,158,11,0.22); }
    .day-badge {
        display:inline-flex; align-items:center;
        background:linear-gradient(135deg,#F59E0B,#FCD34D);
        color:#0A0500; font-weight:700; font-size:.84rem;
        padding:3px 14px; border-radius:100px; margin-bottom:10px;
        font-family:'DM Sans',sans-serif; letter-spacing:.2px;
    }
    .place-row {
        background:rgba(255,255,255,0.045); border-left:3px solid rgba(245,158,11,0.35);
        border-radius:0 9px 9px 0; padding:6px 12px; margin:4px 0;
        color:#CBD5E1; font-size:.85rem; font-family:'DM Sans',sans-serif;
        transition:border-color .13s, background .13s;
    }
    .place-row:hover { border-left-color:#F59E0B; background:rgba(255,255,255,0.065); }
    .cost-total {
        background:linear-gradient(135deg,rgba(16,185,129,.18),rgba(52,211,153,.08));
        border:1px solid rgba(16,185,129,.30); border-radius:11px;
        padding:10px 15px; text-align:center;
        font-size:1.05rem; font-weight:800; color:#34D399;
        margin:10px 0; font-family:'Syne',sans-serif;
    }

    /* Inputs */
    .stTextInput input, div[data-baseweb="input"] input {
        background:#0A1628 !important; border:1.5px solid rgba(148,163,184,0.18) !important;
        border-radius:10px !important; color:#E2E8F0 !important;
        -webkit-text-fill-color:#E2E8F0 !important; caret-color:#F59E0B !important;
        padding:10px 14px !important; font-size:.90rem !important;
        transition:border-color .18s, box-shadow .18s !important;
    }
    .stTextInput input:focus { border-color:#F59E0B !important; box-shadow:0 0 0 3px rgba(245,158,11,0.14) !important; background:#0D1E3A !important; }
    div[data-baseweb="input"] { background:#0A1628 !important; border-radius:10px !important; }
    .stSelectbox > div > div, .stMultiSelect > div > div, .stNumberInput input {
        background:#0A1628 !important; border:1.5px solid rgba(148,163,184,0.18) !important;
        border-radius:10px !important; color:#E2E8F0 !important; -webkit-text-fill-color:#E2E8F0 !important;
    }
    .stTextInput label, .stSelectbox label, .stSlider label, .stRadio label, .stNumberInput label {
        color:rgba(148,163,184,0.65) !important; font-size:.69rem !important;
        font-weight:700 !important; text-transform:uppercase !important; letter-spacing:.65px !important;
    }
    .stButton > button {
        background:linear-gradient(135deg,#F59E0B,#FCD34D) !important;
        color:#0A0500 !important; border:none !important; border-radius:10px !important;
        padding:10px 18px !important; font-weight:700 !important;
        transition:transform .13s, box-shadow .13s !important;
        box-shadow:0 3px 14px rgba(245,158,11,.32) !important;
    }
    .stButton > button:hover { transform:translateY(-2px) !important; box-shadow:0 7px 22px rgba(245,158,11,.46) !important; }
    [data-testid="stLinkButton"] a {
        background:rgba(255,255,255,.055) !important; border:1px solid rgba(255,255,255,.10) !important;
        border-radius:9px !important; color:#CBD5E1 !important; font-size:.80rem !important; font-weight:600 !important;
        padding:7px 12px !important; text-decoration:none !important;
        display:inline-flex !important; align-items:center !important; gap:5px !important; transition:all .13s !important;
    }
    [data-testid="stLinkButton"] a:hover { background:rgba(245,158,11,.12) !important; border-color:rgba(245,158,11,.38) !important; color:#FCD34D !important; }
    .stAlert { border-radius:11px !important; font-size:.84rem !important; }
    </style>
    """, unsafe_allow_html=True)

# ── Main page ─────────────────────────────────────────────────
def itinerary_page(user: dict):
    try:
        if theme:
            theme.apply_global_theme()
    except Exception:
        pass
    _inject_css()

    # Session defaults
    for k, v in [
        ("itinerary_generated", False),
        ("itinerary_data", {}),
        ("trip", {}),
        ("costs", {}),
    ]:
        if k not in st.session_state:
            st.session_state[k] = v

    st.markdown(
        '<div style="padding:6px 0 8px 0;">' +
        '<h1 style="margin:0;font-size:1.45rem;font-weight:800;color:#F8FAFC;">🧳 Travel Itinerary Generator</h1>' +
        f'<p style="color:rgba(255,255,255,0.55);font-size:0.76rem;margin:2px 0 0 0;">Logged in as {user.get("full_name","Traveller")} · AI-powered trip planning</p>' +
        '</div>',
        unsafe_allow_html=True,
    )

    # ── Destination selector ────────────────────────────────
    st.markdown('<div class="itin-card">', unsafe_allow_html=True)
    st.markdown("#### 📍 Select Your Destination")

    colA, colB, colC = st.columns(3)
    with colA:
        country = st.selectbox("Country", list(LOCATION_DATA.keys()), key="itin_country")
    with colB:
        state   = st.selectbox("State / Region", list(LOCATION_DATA[country].keys()), key="itin_state")
    with colC:
        city    = st.selectbox("City", LOCATION_DATA[country][state], key="itin_city")

    col1, col2, col3 = st.columns(3)
    with col1:
        days = st.number_input("Duration (days)", min_value=1, max_value=15, value=3, key="itin_days")
    with col2:
        travel_type = st.radio("Travel Style", ["Budget", "Luxury"], key="itin_type", horizontal=True)
    with col3:
        transport = st.selectbox("Transport Mode", ["Cab", "Metro", "Auto", "Car", "Walking", "Public Transport"], key="itin_transport")

    # Advanced options row
    col4, col5, col6 = st.columns(3)
    with col4:
        activity_filter = st.selectbox("👥 Trip Type", ["All", "👨‍👩‍👧 Family", "💑 Couples", "🧳 Solo", "🏃 Adventure", "🎭 Cultural"], key="itin_activity_filter")
    with col5:
        show_transport_stops = st.toggle("🚌 Show Transport Stops", value=False, key="itin_transport_map")
    with col6:
        tile_style = st.selectbox("🗺️ Map Style", list(TILE_STYLES.keys()), key="itin_tile_style")
    st.markdown('</div>', unsafe_allow_html=True)

    # Validate: origin == destination check
    trip_state = st.session_state.trip
    if trip_state.get("origin_city", "").lower() == city.lower():
        st.warning("⚠️ Origin and destination cannot be the same city.")
        return

    # ── Sidebar: music toggle ──────────────────────────────
    if _AUDIO_OK:
        render_music_toggle()

    # ── Action buttons ──────────────────────────────────────
    cg, cr = st.columns([3, 1])
    with cg:
        generate = st.button("✨ Generate Itinerary", key="itin_gen", use_container_width=True)
    with cr:
        reset = st.button("🔄 Reset", key="itin_reset", use_container_width=True)

    if reset:
        st.session_state.itinerary_generated = False
        st.session_state.itinerary_data      = {}
        st.rerun()

    if generate:
        # ── Log itinerary destination search ──
        if _DB_LOG_OK and st.session_state.get("user"):
            try:
                from log_p import get_db
                _lc = get_db()
                if _lc:
                    _db_log.log_search(_lc, st.session_state.user, city, "itinerary")
                    _lc.close()
            except Exception:
                pass
        with st.spinner(f"Fetching weather & places for **{city}**..."):
            weather = get_weather_by_city(city)
            places_raw = get_places_for_city(city, limit=40)

        if not weather:
            st.error("❌ Could not fetch weather. Check `OPENWEATHER_API_KEY` in `.streamlit/secrets.toml`.")
            return
        if not places_raw:
            st.error("❌ Could not fetch places. Check `geoapify_key` in `.streamlit/secrets.toml`.")
            return

        # Pre-filter: dedup + sort by proximity to city center
        places = _dedup_places(places_raw)
        if weather:
            places = sort_by_proximity(places, weather["lat"], weather["lon"])

        # Show welcome greeting for destination
        play_welcome_greeting(city)

        # Notify user
        st.toast(f"🗺️ Itinerary ready for {city}!", icon="✅")

        st.session_state.itinerary_data = {
            "city": city, "country": country, "state": state,
            "days": int(days), "travel_type": travel_type,
            "transport": transport, "weather": weather, "places": places,
            "activity_filter": activity_filter,
            "tile_style": tile_style,
            "show_transport": show_transport_stops,
        }
        st.session_state.trip.update({
            "country": country, "state": state, "destination_city": city,
            "days": int(days), "travel_type": travel_type, "transport": transport,
            "extras": st.session_state.trip.get("extras", []),
        })

        try:
            from fh import compute_trip_cost
            st.session_state.costs = compute_trip_cost(st.session_state.trip)
        except Exception as e:
            logger.warning("Could not compute costs: %s", e)
            st.session_state.costs = {}

        st.session_state.itinerary_generated = True

        # ── Log itinerary to Excel ──────────────────────────
        if _XL_OK:
            try:
                _user = st.session_state.get("user", {})
                _email = _user.get("email", "unknown") if _user else "unknown"
                _costs = st.session_state.get("costs", {})
                _notes = f"{days}-day trip | {travel_type} | {transport}"
                _xl.log_itinerary(
                    email=_email,
                    destination=f"{city}, {country}",
                    travel_date=str(date.today()),
                    budget=travel_type,
                    notes=_notes,
                )
            except Exception as _xe:
                logger.error("Excel itinerary log failed: %s", _xe)

        st.success(f"✅ Itinerary generated for **{city}**, {country}!")

    if not st.session_state.itinerary_generated:
        st.markdown('<div class="itin-card">', unsafe_allow_html=True)
        st.info("👆 Select your destination above and click **Generate Itinerary** to get started.")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    # ── Display itinerary ───────────────────────────────────
    data            = st.session_state.itinerary_data
    city            = data["city"]
    country         = data.get("country", "India")
    days            = data["days"]
    travel_type     = data["travel_type"]
    transport       = data.get("transport", "Cab")
    weather         = data["weather"]
    places          = data["places"]
    activity_filter = data.get("activity_filter", "All")
    tile_style      = data.get("tile_style", "Street")
    show_transport  = data.get("show_transport", False)
    city_lang       = get_city_language(city)

    st.markdown(
        f'<div style="padding:4px 0 6px 0;">' +
        f'<h2 style="margin:0;font-size:1.20rem;font-weight:700;color:#F8FAFC;">📍 {days}-Day {travel_type} Trip to {city}</h2>' +
        '</div>',
        unsafe_allow_html=True,
    )

    # Weather banner
    st.markdown(
        f'<div style="background:rgba(255,255,255,0.07);border-radius:12px;padding:12px 18px;'
        f'margin-bottom:16px;color:#cbd5e1;font-size:.92rem;">'
        f'{weather.get("emoji","🌡️")} <b>Weather:</b> {weather.get("condition","—")} | '
        f'{weather.get("temp","—")}°C | 💧 {weather.get("humidity","—")}% humidity | '
        f'💨 {weather.get("wind_speed","—")} m/s'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── NLP Itinerary Summary ───────────────────────────────
    with st.expander("🤖 AI Trip Summary", expanded=False):
        summary = _summarize_itinerary_nlp(city, days, places)
        st.markdown(summary)

    per_day      = max(1, len(places) // days)
    daily_places = [places[i * per_day : (i + 1) * per_day] for i in range(days)]
    full_text    = []
    grand_total  = 0
    skipped_days = set()

    # Mark top 3 attractions across entire trip
    if places:
        get_top_attractions(places, n=3)

    for day_idx in range(days):
        day_places = daily_places[day_idx] if day_idx < len(daily_places) else []

        st.markdown('<div class="itin-card">', unsafe_allow_html=True)

        # Day header with Skip toggle
        dcol1, dcol2 = st.columns([5, 1])
        with dcol1:
            st.markdown(f'<div class="day-badge">🗓️ Day {day_idx + 1} — {city}</div>', unsafe_allow_html=True)
        with dcol2:
            skip_day = st.toggle("Skip", key=f"skip_day_{day_idx}", value=False)

        if skip_day:
            skipped_days.add(day_idx)
            st.info(f"⏭️ Day {day_idx + 1} skipped. Tap toggle to restore.")
            st.markdown('</div>', unsafe_allow_html=True)
            continue

        # Day chime greeting
        if day_idx == 0 and _AUDIO_OK:
            play_day_chime(day_idx + 1, city, travel_type)

        # Daily toast notification
        if day_idx < 3:
            st.toast(f"📅 Day {day_idx+1}: {len(day_places)} places planned!", icon="🗺️")

        if not day_places:
            st.info("No places for this day. Try increasing trip radius in places_service.")
            st.markdown('</div>', unsafe_allow_html=True)
            continue

        hotels = get_hotels_near(day_places[0]["lat"], day_places[0]["lon"], city=city)
        foods  = get_food_near(day_places[0]["lat"],  day_places[0]["lon"], city=city)

        # Fetch transport stops if toggled
        transport_stops = []
        if show_transport:
            transport_stops = fetch_transport_stops_osm(day_places[0]["lat"], day_places[0]["lon"])

        # Timed schedule with color-coding
        start_time = datetime.strptime("09:00", "%H:%M")
        day_text   = [f"Day {day_idx + 1}"]

        st.markdown("**📅 Day Schedule:**")
        for i, p in enumerate(day_places):
            time_str = (start_time + timedelta(hours=2 * i)).strftime("%I:%M %p")
            is_top   = p.get("top_pick", False)
            duration = _estimate_duration(p["name"])
            tags     = _assign_tags(p["name"])
            tag_str  = " ".join(tags[:2]) if tags else ""
            top_icon = "⭐ " if is_top else ""
            row_style = (
                "border-left:4px solid #F6A81A;"
                if is_top
                else "border-left:3px solid rgba(255,255,255,0.3);"
            )
            place_html = (
                f'<div class="place-row" style="{row_style}">' +
                f'⏰ <b>{time_str}</b> — {top_icon}{p["name"]} ' +
                f'<span style="font-size:0.78rem;color:rgba(255,255,255,0.5);">' +
                f'({duration} min) {tag_str}</span></div>'
            )
            st.markdown(place_html, unsafe_allow_html=True)
            day_text.append(p["name"])

        # Lunch break marker
        lunch_idx = len(day_places) // 2
        lunch_time = (start_time + timedelta(hours=2 * lunch_idx)).strftime("%I:%M %p")
        lunch_html = (
            f'<div class="place-row" style="border-left:3px solid #e74c3c;background:rgba(231,76,60,0.1);">' +
            f'🍽️ <b>{lunch_time}</b> — Lunch Break (explore local restaurants)</div>'
        )
        st.markdown(lunch_html, unsafe_allow_html=True)

        full_text.append(", ".join(day_text))

        # Cost breakdown
        cost = calculate_daily_cost(country, travel_type, len(day_places), transport)
        grand_total += cost["total"]

        with st.expander(f"💰 Daily Cost Breakdown — ₹{cost['total']:,.0f}", expanded=False):
            for k, v in cost.items():
                if k != "total":
                    st.markdown(f"**{k}:** ₹{v:,.0f}")
            st.markdown(f"**🧮 Day Total:** ₹{cost['total']:,.0f}")

        # Clothing & packing (day-specific with weather)
        outfit = outfit_and_pack(weather.get("temp", 25), weather.get("condition", "clear"))
        with st.expander(f"👕 Day {day_idx+1} Clothing & Packing", expanded=False):
            st.markdown(f"📝 {outfit['summary']}")
            if outfit["accessories"]:
                st.markdown("**🎒 Accessories:** " + " · ".join(outfit["accessories"]))
            if outfit["packlist"]:
                st.markdown("**📦 Pack:** " + " · ".join(outfit["packlist"]))

        # Platform booking links
        with st.expander("🔗 Book Hotels & Restaurants", expanded=False):
            h_links = hotel_platform_links(city)
            f_links = food_platform_links(city)

            st.markdown("**🏨 Hotels:**")
            hcols = st.columns(min(len(h_links), 4))
            for i, (label, url) in enumerate(h_links.items()):
                with hcols[i % 4]:
                    st.link_button(f"🔗 {label}", url, use_container_width=True)

            st.markdown("**🍽️ Food:**")
            fcols = st.columns(min(len(f_links), 3))
            for i, (label, url) in enumerate(f_links.items()):
                with fcols[i % 3]:
                    st.link_button(f"🔗 {label}", url, use_container_width=True)

        # Map with enhanced features
        if _MAP_SERVICE_OK:
            try:
                day_map = _gen_map_service(
                    day_places[0]["lat"], day_places[0]["lon"],
                    day_places, hotels, foods,
                    transport_stops=transport_stops,
                    city_name=city,
                    tile_style=tile_style,
                    highlight_top=True,
                )
            except Exception:
                day_map = _build_map(day_places, hotels, foods)
        else:
            day_map = _build_map(day_places, hotels, foods)
        st_folium(day_map, height=320, width="100%", key=f"itin_map_{day_idx}")

        _safety_tips()
        st.markdown('</div>', unsafe_allow_html=True)

    # ── TTS narration (language-aware) ──────────────────────
    if _AUDIO_OK and full_text:
        try:
            narrate_itinerary_day(
                1, city,
                [p["name"] for p in (daily_places[0] if daily_places else [])[:5]],
                lang=city_lang,
                autoplay=True,
            )
        except Exception:
            pass
    else:
        try:
            from gtts import gTTS
            narration = f"Your {days}-day {travel_type} trip to {city}. " + ". ".join(full_text[:3])
            tts = gTTS(text=narration, lang="en")
            fp  = io.BytesIO()
            tts.write_to_fp(fp)
            fp.seek(0)
            b64 = base64.b64encode(fp.read()).decode()
            st.markdown(
                f'<audio autoplay hidden><source src="data:audio/mp3;base64,{b64}" type="audio/mp3"></audio>',
                unsafe_allow_html=True,
            )
        except Exception:
            pass

    # ── Grand total ─────────────────────────────────────────
    session_total = st.session_state.costs.get("total", grand_total)
    st.markdown(
        f'<div class="cost-total">💰 Total Estimated Trip Cost: ₹{session_total:,.0f}</div>',
        unsafe_allow_html=True,
    )

    # ── Weather advice ──────────────────────────────────────
    if weather.get("advice"):
        st.info(f"🌤️ Travel Tip: {weather['advice']}")

    # ── Actions ─────────────────────────────────────────────
    st.markdown("---")
    ca, cb, cc = st.columns(3)
    with ca:
        if st.button("🧾 Trip Summary", key="itin_summary", use_container_width=True):
            st.session_state.sidebar_page = "Home"
            st.session_state.show_feedback_form = True
            st.rerun()
    with cb:
        if st.button("💰 Full Dashboard", key="itin_dash", use_container_width=True):
            st.session_state.sidebar_page = "Dashboard"
            st.rerun()
    with cc:
        if st.button("📝 Leave Feedback", key="itin_feedback", use_container_width=True):
            st.session_state.sidebar_page = "📝 Feedback"
            st.rerun()

    if st.button("🔄 Reset Itinerary", key="itin_reset_bottom", use_container_width=True):
            st.session_state.itinerary_generated = False
            st.session_state.itinerary_data      = {}
            st.rerun()

    st.caption("💡 Smart Atlas uses an Aggregator + Redirect model. All booking links redirect to trusted external platforms.")
