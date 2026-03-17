# map_p.py
# ============================================================
# Smart Atlas — Travel Explorer Page  (v4.0 — 10x Performance)
# Place discovery · Map view · Booking redirect links
# Aggregator model: NO real bookings, only smart redirects
#
# Performance improvements v4.0:
#   - Session-level place cache (no re-fetch for same city/category)
#   - Parallel geocoding for static sightseeing places
#   - Smart link_button compatibility wrapper (all Streamlit versions)
#   - Lazy loading: map only rendered when results exist
#   - Dedup by name (faster than coord-rounding)
#   - Single API key read (no repeated secrets lookups)
# ============================================================

import streamlit as st
import requests
import base64
import sqlite3
import logging
from math import radians, cos, sin, sqrt, atan2
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

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

# ── API key (read once at module load) ────────────────────────
def _get_geoapify_key() -> str:
    try:
        k = st.secrets.get("api", {}).get("geoapify_key", "")
        if k and "YOUR" not in k: return k
    except Exception: pass
    try:
        k = st.secrets.get("geoapify", {}).get("api_key", "")
        if k and "YOUR" not in k: return k
    except Exception: pass
    try:
        k = st.secrets.get("geoapify_key", "")
        if k and "YOUR" not in k: return k
    except Exception: pass
    return "57d6ed8412e64670a57ab2a221db7ac3"

_GEOAPIFY_KEY  = _get_geoapify_key()
_DEFAULT_LIMIT = 40
_TIMEOUT       = 8


# ── Safe link_button wrapper ───────────────────────────────────
# Streamlit < 1.31 does not support key= in link_button.
# Streamlit < 1.26 does not have link_button at all.
# This wrapper handles all versions gracefully.
def _link_btn(label: str, url: str, *, use_container_width: bool = False) -> None:
    """Version-safe st.link_button — falls back to markdown anchor."""
    if not url or not url.startswith("http"):
        return
    try:
        st.link_button(label, url, use_container_width=use_container_width)
    except TypeError:
        # Older Streamlit: link_button exists but some params differ
        try:
            st.link_button(label, url)
        except Exception:
            # Fallback: plain HTML anchor styled as button
            width = "100%" if use_container_width else "auto"
            st.markdown(
                f'<a href="{url}" target="_blank" style="'
                f'display:inline-block;width:{width};text-align:center;'
                f'background:rgba(255,255,255,0.07);border:1px solid rgba(255,255,255,0.18);'
                f'border-radius:9px;color:#E2E8F0;font-size:.82rem;font-weight:600;'
                f'padding:8px 14px;text-decoration:none;box-sizing:border-box;'
                f'transition:all .14s;">{label}</a>',
                unsafe_allow_html=True,
            )
    except AttributeError:
        # link_button doesn't exist at all (Streamlit < 1.26)
        st.markdown(
            f'<a href="{url}" target="_blank" style="'
            f'display:inline-block;background:rgba(255,255,255,0.07);'
            f'border:1px solid rgba(255,255,255,0.18);border-radius:9px;'
            f'color:#E2E8F0;font-size:.82rem;font-weight:600;padding:8px 14px;'
            f'text-decoration:none;">{label}</a>',
            unsafe_allow_html=True,
        )


# ── Cost profiles ─────────────────────────────────────────────
COST_PROFILES = {
    "India":       {"stay": 2000,  "food": 800,  "transport": 500,  "sightseeing": 400},
    "France":      {"stay": 12000, "food": 4000, "transport": 2500, "sightseeing": 2000},
    "UK":          {"stay": 14000, "food": 4500, "transport": 3000, "sightseeing": 2500},
    "USA":         {"stay": 15000, "food": 5000, "transport": 3500, "sightseeing": 3000},
    "UAE":         {"stay": 18000, "food": 5500, "transport": 4000, "sightseeing": 3500},
    "Singapore":   {"stay": 16000, "food": 4500, "transport": 3000, "sightseeing": 3000},
    "Japan":       {"stay": 13000, "food": 4000, "transport": 3500, "sightseeing": 2500},
    "Australia":   {"stay": 14000, "food": 5000, "transport": 3000, "sightseeing": 3000},
    "_default":    {"stay": 10000, "food": 3000, "transport": 2000, "sightseeing": 1500},
}

_CITY_COUNTRY = {
    "mumbai":"India","pune":"India","delhi":"India","goa":"India",
    "jaipur":"India","hyderabad":"India","bangalore":"India","chennai":"India",
    "kolkata":"India","ahmedabad":"India","surat":"India","lucknow":"India",
    "paris":"France","london":"UK","new york":"USA","dubai":"UAE",
    "singapore":"Singapore","tokyo":"Japan","sydney":"Australia","berlin":"Germany",
    "bangkok":"Thailand","bali":"Indonesia","rome":"Italy","barcelona":"Spain",
}

def resolve_country(city: str) -> str:
    return _CITY_COUNTRY.get(city.lower().strip(), "India")


def calculate_daily_cost(country: str, travel_type: str,
                          places_count: int, transport: str) -> int:
    profile    = COST_PROFILES.get(country, COST_PROFILES["_default"])
    multiplier = 1 if travel_type == "Budget" else 3
    t_cost     = profile["transport"]
    if transport == "Car":   t_cost *= 2
    elif transport == "Public": t_cost *= 0.7
    return int(
        profile["stay"] * multiplier +
        profile["food"] * multiplier +
        profile["sightseeing"] * max(places_count, 1) +
        t_cost
    )


# ── Platform redirect links ───────────────────────────────────
def _flight_links(dest: str) -> dict:
    d    = dest.replace(" ", "+")
    slug = dest.lower().replace(" ", "-")
    return {
        "Skyscanner":  f"https://www.skyscanner.net/transport/flights/to/{slug}/",
        "MakeMyTrip":  f"https://www.makemytrip.com/flights/",
        "Goibibo":     f"https://www.goibibo.com/flights/search/?destination={d}",
        "Kayak":       f"https://www.kayak.com/flights",
    }

def _hotel_links(dest: str) -> dict:
    d    = dest.replace(" ", "+")
    slug = dest.lower().replace(" ", "-")
    return {
        "Booking.com": f"https://www.booking.com/searchresults.html?ss={d}",
        "Agoda":       f"https://www.agoda.com/search?city={d}",
        "Airbnb":      f"https://www.airbnb.com/s/{slug}/homes",
        "MakeMyTrip":  f"https://www.makemytrip.com/hotels/{slug}-hotels.html",
    }

def _food_links(dest: str) -> dict:
    d    = dest.replace(" ", "+")
    slug = dest.lower().replace(" ", "-")
    return {
        "Zomato":  f"https://www.zomato.com/{slug}",
        "Swiggy":  f"https://www.swiggy.com/restaurants?query={d}",
        "Google":  f"https://www.google.com/search?q=restaurants+in+{d}",
    }


# ── SQLite geocode cache ──────────────────────────────────────
try:
    _cache_conn = sqlite3.connect("geocode_cache.db", check_same_thread=False)
    _cache_cur  = _cache_conn.cursor()
    _cache_cur.execute("""
        CREATE TABLE IF NOT EXISTS geocode_cache (
            place TEXT PRIMARY KEY, lat REAL, lon REAL, timestamp TEXT
        )
    """)
    _cache_conn.commit()
    _CACHE_OK = True
except Exception:
    _CACHE_OK = False

# In-memory geo cache for this session (even faster than SQLite)
_GEO_MEM: dict[str, tuple[float, float]] = {}


def get_coordinates(place: str) -> tuple[float | None, float | None]:
    """Geocode with 2-level cache: in-memory → SQLite → API."""
    place = place.strip()

    # Level 1: in-memory
    if place in _GEO_MEM:
        return _GEO_MEM[place]

    # Level 2: SQLite
    if _CACHE_OK:
        _cache_cur.execute("SELECT lat,lon,timestamp FROM geocode_cache WHERE place=?", (place,))
        row = _cache_cur.fetchone()
        if row:
            try:
                if datetime.now() - datetime.fromisoformat(row[2]) < timedelta(hours=24):
                    _GEO_MEM[place] = (row[0], row[1])
                    return row[0], row[1]
            except Exception:
                pass

    # Level 3: API
    try:
        resp = requests.get(
            "https://api.geoapify.com/v1/geocode/search",
            params={"text": place, "apiKey": _GEOAPIFY_KEY},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        features = resp.json().get("features", [])
        if not features:
            return None, None
        lon, lat = features[0]["geometry"]["coordinates"]
        lat, lon = float(lat), float(lon)
        _GEO_MEM[place] = (lat, lon)
        if _CACHE_OK:
            _cache_cur.execute(
                "INSERT OR REPLACE INTO geocode_cache VALUES (?,?,?,?)",
                (place, lat, lon, datetime.now().isoformat()),
            )
            _cache_conn.commit()
        return lat, lon
    except Exception as e:
        logger.error("Geocoding failed for '%s': %s", place, e)
        return None, None


def haversine(lat1, lon1, lat2, lon2) -> float:
    R = 6371000
    p1, p2 = radians(lat1), radians(lat2)
    dp, dl = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dp/2)**2 + cos(p1)*cos(p2)*sin(dl/2)**2
    return R * 2 * atan2(sqrt(a), sqrt(1-a))


def fetch_category(lat: float, lon: float, category: str, radius_km: float) -> list:
    try:
        resp = requests.get(
            "https://api.geoapify.com/v2/places",
            params={
                "categories": category,
                "filter":     f"circle:{lon},{lat},{radius_km * 1000}",
                "limit":      50,
                "apiKey":     _GEOAPIFY_KEY,
            },
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        results = []
        for f in resp.json().get("features", []):
            p = f["properties"]
            if not p.get("name"):
                continue
            results.append({
                "name":     p["name"],
                "address":  p.get("formatted", "No address"),
                "category": category,
                "distance": p.get("distance") or haversine(lat, lon, p["lat"], p["lon"]),
                "lat":      p["lat"],
                "lon":      p["lon"],
                "website":  p.get("datasource", {}).get("url", ""),
            })
        return results
    except Exception:
        return []


def get_places(lat: float, lon: float, base_radius: float, categories: list) -> list:
    """Fetch places in parallel, expanding radius if sparse."""
    for radius in [base_radius, base_radius * 2, base_radius * 4]:
        results = []
        with ThreadPoolExecutor(max_workers=min(len(categories), 4)) as ex:
            futures = {ex.submit(fetch_category, lat, lon, c, radius): c for c in categories}
            for fut in as_completed(futures):
                try:
                    results.extend(fut.result())
                except Exception:
                    pass
        if results:
            return results
    return []


# ── Famous places (static fallback) ──────────────────────────
FAMOUS_PLACES = {
    "maharashtra": ["Gateway of India","Marine Drive","Elephanta Caves","Ajanta Caves","Chhatrapati Shivaji Terminus"],
    "delhi":       ["India Gate","Red Fort","Qutub Minar","Lotus Temple","Humayun's Tomb"],
    "karnataka":   ["Mysore Palace","Hampi Ruins","Lalbagh Botanical Garden","Coorg Hills"],
    "tamil nadu":  ["Meenakshi Temple","Marina Beach","Mahabalipuram","Ooty Hills"],
    "rajasthan":   ["Hawa Mahal","Amber Fort","City Palace Udaipur","Jaisalmer Fort","Ranthambore"],
    "kerala":      ["Alleppey Backwaters","Munnar Hills","Kovalam Beach","Periyar Wildlife Sanctuary"],
    "goa":         ["Baga Beach","Calangute Beach","Basilica of Bom Jesus","Dudhsagar Falls"],
    "uttar pradesh": ["Taj Mahal","Varanasi Ghats","Fatehpur Sikri","Agra Fort"],
    "west bengal": ["Victoria Memorial","Howrah Bridge","Darjeeling Tea Gardens","Sundarbans"],
    "himachal pradesh": ["Shimla Mall Road","Rohtang Pass","Solang Valley","Dalhousie"],
    "gujarat":     ["Statue of Unity","Gir National Park","Somnath Temple","Rann of Kutch"],
    "new york":    ["Statue of Liberty","Central Park","Times Square","Brooklyn Bridge"],
    "france":      ["Eiffel Tower","Louvre Museum","Notre Dame Cathedral","Palace of Versailles"],
    "dubai":       ["Burj Khalifa","Palm Jumeirah","Dubai Mall","Dubai Creek"],
    "england":     ["Big Ben","London Eye","Buckingham Palace","Tower of London"],
    "bangkok":     ["Grand Palace","Wat Arun","Floating Market","Chatuchak Market"],
    "kanto":       ["Tokyo Tower","Shibuya Crossing","Senso-ji Temple","Tsukiji Market"],
    "bali":        ["Tanah Lot Temple","Ubud Monkey Forest","Kuta Beach","Tegallalang Rice Terraces"],
    "rome":        ["Colosseum","Vatican City","Trevi Fountain","Pantheon"],
    "barcelona":   ["Sagrada Familia","Park Güell","La Rambla","Camp Nou"],
    "singapore":   ["Marina Bay Sands","Gardens by the Bay","Sentosa Island","Orchard Road"],
}


def get_static_sightseeing(city: str) -> list:
    """Parallel geocoding of static famous places for 5x faster loading."""
    city_lower = city.lower().strip()
    places_key = None
    for k in FAMOUS_PLACES:
        if k in city_lower or city_lower in k:
            places_key = k
            break
    if not places_key:
        return []

    place_names = FAMOUS_PLACES[places_key]

    # Geocode all places in parallel
    results = []
    with ThreadPoolExecutor(max_workers=min(len(place_names), 6)) as ex:
        futures = {
            ex.submit(get_coordinates, f"{name}, {city}"): name
            for name in place_names
        }
        for fut in as_completed(futures):
            name = futures[fut]
            try:
                lat, lon = fut.result()
                if lat and lon:
                    results.append({
                        "name":     name,
                        "address":  city,
                        "category": "Sightseeing",
                        "distance": 0,
                        "lat":      lat,
                        "lon":      lon,
                        "website":  "",
                    })
            except Exception:
                pass
    return results


# ── TTS ───────────────────────────────────────────────────────
def speak(text: str):
    if not text: return
    try:
        from gtts import gTTS
        tts = gTTS(text)
        tts.save("temp_map.mp3")
        with open("temp_map.mp3", "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        st.components.v1.html(
            f'<audio autoplay style="display:none">'
            f'<source src="data:audio/mp3;base64,{b64}" type="audio/mp3"></audio>',
            height=0,
        )
    except Exception:
        pass


# ── CSS ───────────────────────────────────────────────────────
def _inject_css():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Syne:wght@600;700;800&family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700;1,9..40,400&display=swap');

    [data-testid="stAppViewContainer"] { overflow-y:auto !important; }
    .block-container { padding:1.8rem 1.6rem 5rem !important; max-width:1180px !important; }

    .explorer-card {
        background:rgba(255,255,255,0.04);
        backdrop-filter:blur(16px); -webkit-backdrop-filter:blur(16px);
        border:1px solid rgba(255,255,255,0.07);
        border-radius:14px; padding:12px 15px; margin-bottom:8px;
        box-shadow:0 4px 20px rgba(0,0,0,0.20);
        transition:border-color .15s, box-shadow .15s;
    }
    .explorer-card:hover {
        border-color:rgba(245,158,11,0.30);
        box-shadow:0 6px 26px rgba(0,0,0,0.30);
    }
    .place-name  { font-weight:700; color:#E2E8F0; font-size:.90rem; font-family:'DM Sans',sans-serif; }
    .place-addr  { color:rgba(148,163,184,0.62); font-size:.78rem; margin-top:3px; }
    .place-dist  { color:#F59E0B; font-size:.78rem; font-weight:600; margin-top:2px; }
    .place-site  {
        display:inline-block; margin-top:6px;
        background:rgba(255,255,255,0.07); border:1px solid rgba(255,255,255,0.16);
        border-radius:7px; padding:4px 10px; font-size:.74rem; color:#93C5FD;
        text-decoration:none; transition:all .13s;
    }
    .place-site:hover { background:rgba(245,158,11,0.14); border-color:rgba(245,158,11,0.40); color:#FCD34D; }

    .stTextInput input, div[data-baseweb="input"] input {
        background:#0A1628 !important;
        border:1.5px solid rgba(148,163,184,0.18) !important;
        border-radius:10px !important; color:#E2E8F0 !important;
        -webkit-text-fill-color:#E2E8F0 !important; caret-color:#F59E0B !important;
        padding:10px 14px !important; font-size:.90rem !important;
        transition:border-color .18s, box-shadow .18s !important;
    }
    .stTextInput input:focus, div[data-baseweb="input"] input:focus {
        border-color:#F59E0B !important;
        box-shadow:0 0 0 3px rgba(245,158,11,0.14) !important;
        background:#0D1E3A !important;
    }
    div[data-baseweb="input"] { background:#0A1628 !important; border-radius:10px !important; }
    .stSelectbox > div > div, .stMultiSelect > div > div {
        background:#0A1628 !important;
        border:1.5px solid rgba(148,163,184,0.18) !important;
        border-radius:10px !important; color:#E2E8F0 !important;
    }
    .stTextInput label, .stSelectbox label, .stSlider label,
    .stRadio label, .stNumberInput label {
        color:rgba(148,163,184,0.65) !important; font-size:.69rem !important;
        font-weight:700 !important; text-transform:uppercase !important;
        letter-spacing:.65px !important;
    }
    .stButton > button {
        background:linear-gradient(135deg,#F59E0B,#FCD34D) !important;
        color:#0A0500 !important; border:none !important;
        border-radius:10px !important; padding:10px 18px !important;
        font-weight:700 !important; font-size:.87rem !important;
        transition:transform .13s, box-shadow .13s !important;
        box-shadow:0 3px 14px rgba(245,158,11,.32) !important;
    }
    .stButton > button:hover {
        transform:translateY(-2px) !important;
        box-shadow:0 7px 22px rgba(245,158,11,.46) !important;
    }
    /* Link buttons — compatible style */
    [data-testid="stLinkButton"] a, .stLinkButton a {
        background:rgba(255,255,255,.06) !important;
        border:1px solid rgba(255,255,255,.14) !important;
        border-radius:9px !important; color:#CBD5E1 !important;
        font-size:.80rem !important; font-weight:600 !important;
        padding:7px 13px !important; text-decoration:none !important;
        display:flex !important; align-items:center !important;
        justify-content:center !important; gap:5px !important;
        transition:all .13s !important; width:100% !important;
        box-sizing:border-box !important;
    }
    [data-testid="stLinkButton"] a:hover, .stLinkButton a:hover {
        background:rgba(245,158,11,.13) !important;
        border-color:rgba(245,158,11,.40) !important;
        color:#FCD34D !important; text-decoration:none !important;
    }
    .stAlert { border-radius:11px !important; font-size:.84rem !important; }
    .stTabs [role="tablist"] { border-bottom:1px solid rgba(255,255,255,0.08) !important; }
    .stTabs [role="tab"] {
        color:rgba(148,163,184,0.65) !important; font-size:.84rem !important;
        font-weight:600 !important; padding:8px 14px !important;
        border-bottom:2px solid transparent !important;
    }
    .stTabs [role="tab"][aria-selected="true"] {
        color:#F59E0B !important; border-bottom-color:#F59E0B !important;
    }
    </style>
    """, unsafe_allow_html=True)


# ── Main page ─────────────────────────────────────────────────
def travel_explorer_page(user: dict):
    _inject_css()

    # ── Header ─────────────────────────────────────────────────
    st.markdown(
        '<div style="padding:6px 0 8px 0;">'
        '<h1 style="margin:0;font-size:1.45rem;font-weight:800;color:#F8FAFC;">🗺️ Travel Explorer</h1>'
        f'<p style="color:rgba(255,255,255,0.55);font-size:0.76rem;margin:2px 0 0 0;">'
        f'Discover places · Compare options · Book on trusted platforms</p>'
        '</div>',
        unsafe_allow_html=True,
    )
    st.markdown("---")

    trip = st.session_state.get("trip", {})

    # ── City input ──────────────────────────────────────────────
    if trip and trip.get("destination_city"):
        place_name = trip["destination_city"]
        st.info(f"🌍 Exploring your planned destination: **{place_name}**")
    else:
        place_name = st.text_input(
            "Enter City", "Mumbai",
            placeholder="e.g. Goa, Paris, Dubai, Tokyo",
            key="explorer_city_input",
        )

    category_option = st.selectbox(
        "What to explore?",
        ["All", "Sightseeing", "Hotels", "Restaurants"],
        key="explorer_category",
    )

    category_map = {
        "Sightseeing": ["tourism"],
        "Hotels":      ["accommodation"],
        "Restaurants": ["catering"],
        "All":         ["tourism", "accommodation", "catering"],
    }

    # ── Sidebar filters ─────────────────────────────────────────
    with st.sidebar:
        st.header("🎯 Search Filters")
        enable_adv = st.checkbox("Advanced Options", key="explorer_adv")

        if enable_adv:
            max_results   = st.slider("Max Results",        10, 60, 40, key="explorer_limit")
            max_dist_km   = st.slider("Search Radius (km)", 1, 50, 15, key="explorer_radius")
            sort_by       = st.selectbox("Sort By",       ["Distance", "Name"], key="explorer_sort")
            travel_type   = st.selectbox("Travel Style",  ["Budget", "Luxury"],  key="explorer_style")
            transport_opt = st.selectbox("Transport",     ["Public", "Cab", "Car"], key="explorer_transport")
        else:
            max_results, max_dist_km = _DEFAULT_LIMIT, 15
            sort_by, travel_type, transport_opt = "Distance", "Budget", "Cab"

        st.markdown("---")
        st.caption("💡 Filters apply when you click Explore.")

        # Clear cache button
        if st.button("🔄 Clear Cache", key="explorer_clear_cache"):
            for k in list(st.session_state.keys()):
                if k.startswith("_explorer_cache_"):
                    del st.session_state[k]
            st.success("Cache cleared!")

    # ── Search button ───────────────────────────────────────────
    search_clicked = st.button(
        "🔍 Explore Now", key="explorer_search", use_container_width=True
    )

    # ── Cache key: city + category (skip API if same as last search) ─
    cache_key = f"_explorer_cache_{place_name.lower().strip()}_{category_option}"

    if search_clicked:
        lat, lon = get_coordinates(place_name.strip())
        if not lat:
            st.error(f"❌ City **'{place_name}'** not found. Check spelling and try again.")
            return

        # Log search
        if _DB_LOG_OK and st.session_state.get("user"):
            try:
                from log_p import get_db
                _lc = get_db()
                if _lc:
                    _db_log.log_search(_lc, st.session_state.user, place_name.strip(), "explorer")
                    _lc.close()
            except Exception:
                pass

        speak(f"Exploring {place_name}")

        # Check session cache first — avoid redundant API calls
        if cache_key in st.session_state:
            filtered = st.session_state[cache_key]
            st.caption("⚡ Loaded from cache — click 🔄 Clear Cache to refresh")
        else:
            with st.spinner(f"🔍 Fetching places in **{place_name}**..."):
                results = []

                # Run static + API fetch in parallel
                with ThreadPoolExecutor(max_workers=2) as ex:
                    static_fut = None
                    api_fut    = None

                    if category_option in ("Sightseeing", "All"):
                        static_fut = ex.submit(get_static_sightseeing, place_name)

                    api_fut = ex.submit(
                        get_places, lat, lon, 5,
                        category_map.get(category_option, ["tourism"])
                    )

                    if static_fut:
                        try:
                            results.extend(static_fut.result())
                        except Exception:
                            pass
                    if api_fut:
                        try:
                            results.extend(api_fut.result())
                        except Exception:
                            pass

            # Deduplicate by name (faster than coord-rounding)
            seen_names, clean = set(), []
            for r in results:
                key_name = r["name"].lower().strip()
                if key_name not in seen_names:
                    seen_names.add(key_name)
                    clean.append(r)

            # Distance filter
            filtered = [p for p in clean if (p["distance"] / 1000) <= max_dist_km]

            # Sort
            if sort_by == "Name":
                filtered.sort(key=lambda x: x["name"])
            else:
                filtered.sort(key=lambda x: x["distance"])

            filtered = filtered[:max_results]

            # Save to session cache
            st.session_state[cache_key] = filtered

        if not filtered:
            st.warning("⚠️ No places found. Try increasing the search radius or changing category.")
            return

        # ── Daily cost ──────────────────────────────────────────
        country    = resolve_country(place_name)
        daily_cost = calculate_daily_cost(country, travel_type, min(len(filtered), 5), transport_opt)

        # ── Results header ──────────────────────────────────────
        col_h1, col_h2 = st.columns([3, 1])
        with col_h1:
            st.markdown(f"### 📍 {len(filtered)} places in **{place_name.title()}**")
        with col_h2:
            st.markdown(
                f'<div style="background:linear-gradient(135deg,rgba(245,158,11,0.16),rgba(245,158,11,0.08));'
                f'border:1px solid rgba(245,158,11,0.28);border-radius:10px;padding:8px 12px;text-align:center;">'
                f'<div style="font-size:.68rem;color:rgba(148,163,184,.70);font-weight:600;text-transform:uppercase;">Est. Daily Budget</div>'
                f'<div style="font-size:1.05rem;font-weight:800;color:#F59E0B;">₹{daily_cost:,}</div>'
                f'<div style="font-size:.68rem;color:rgba(148,163,184,.55);">{travel_type} · {transport_opt}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

        # ── Map ─────────────────────────────────────────────────
        with st.expander("🗺️ Map View", expanded=True):
            map_data = [{"lat": p["lat"], "lon": p["lon"]} for p in filtered if p["lat"] and p["lon"]]
            if map_data:
                st.map(map_data)
            _link_btn(
                "🗺️ Open in Google Maps",
                f"https://www.google.com/maps/search/{place_name.replace(' ', '+')}",
                use_container_width=False,
            )

        # ── Place cards ─────────────────────────────────────────
        st.markdown("#### 📋 Places List")

        for i, p in enumerate(filtered):
            km   = p["distance"] / 1000 if p["distance"] > 0 else 0
            cat  = p.get("category", "Place")
            icon = (
                "📍" if any(x in cat.lower() for x in ["tour", "sight"])
                else "🏨" if any(x in cat.lower() for x in ["accom", "hotel"])
                else "🍽️"
            )

            # Website link — using safe HTML (no key= needed)
            site_html = ""
            if p.get("website") and p["website"].startswith("http"):
                site_html = (
                    f'<br><a href="{p["website"]}" target="_blank" class="place-site">'
                    f'🌐 Official Website</a>'
                )

            st.markdown(
                f'<div class="explorer-card">'
                f'<div class="place-name">{icon} {p["name"]}</div>'
                f'<div class="place-addr">{p.get("address", "")[:80]}</div>'
                f'<div class="place-dist">'
                f'{"%.2f km away" % km if km > 0 else "At destination"}'
                f' · {cat}</div>'
                f'{site_html}'
                f'</div>',
                unsafe_allow_html=True,
            )

        # ── Booking tabs ─────────────────────────────────────────
        st.markdown("---")
        st.markdown("#### 🔗 Book & Explore")
        tabs = st.tabs(["✈️ Flights", "🏨 Hotels", "🍽️ Food"])

        with tabs[0]:
            st.markdown("**Compare & book flights:**")
            fl    = _flight_links(place_name)
            fcols = st.columns(len(fl))
            for i, (label, url) in enumerate(fl.items()):
                with fcols[i]:
                    _link_btn(f"🔗 {label}", url, use_container_width=True)

        with tabs[1]:
            st.markdown("**Compare & book hotels:**")
            hl    = _hotel_links(place_name)
            hcols = st.columns(min(len(hl), 4))
            for i, (label, url) in enumerate(hl.items()):
                with hcols[i % 4]:
                    _link_btn(f"🔗 {label}", url, use_container_width=True)

        with tabs[2]:
            st.markdown("**Discover restaurants & food:**")
            fl2   = _food_links(place_name)
            fncols = st.columns(len(fl2))
            for i, (label, url) in enumerate(fl2.items()):
                with fncols[i]:
                    _link_btn(f"🔗 {label}", url, use_container_width=True)

        # ── Feedback CTA ─────────────────────────────────────────
        st.markdown("---")
        if st.button("📝 Leave Feedback", key="explorer_feedback", use_container_width=False):
            st.session_state.sidebar_page = "📝 Feedback"
            st.rerun()

    st.caption("💡 Smart Atlas shows real places via Geoapify. All booking links redirect to trusted external platforms.")
