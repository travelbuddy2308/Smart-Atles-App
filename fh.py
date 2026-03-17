# fh.py
# ============================================================
# Smart Atlas — Trip Planner & Cost Dashboard
# Aggregator model: smart cost estimates + redirect booking links
# ============================================================

import streamlit as st
import datetime
import pandas as pd
import altair as alt
import base64
import logging

logger = logging.getLogger(__name__)

# ── TTS helper (fail-safe) ────────────────────────────────────
def speak(text: str):
    if not text or not text.strip():
        return
    try:
        from gtts import gTTS
        tts = gTTS(text)
        tts.save("temp_fh.mp3")
        with open("temp_fh.mp3", "rb") as f:
            b64_audio = base64.b64encode(f.read()).decode()
        st.components.v1.html(
            f'<audio autoplay style="display:none">'
            f'<source src="data:audio/mp3;base64,{b64_audio}" type="audio/mp3"></audio>',
            height=0, width=0,
        )
    except Exception:
        pass


# ── Cost profiles (extensible) ────────────────────────────────
_DEFAULT_BASE_COSTS = {
    "transport": {"Bus": 1200, "Train": 1800, "Flight": 3500},
    "hotel_per_night": {
        "Low":    800,
        "Medium": 1500,
        "Luxury": 2500,
    },
    "activities_per_day": 600,
    "extras": {
        "Meals":     300,
        "Insurance": 200,
        "Visa":      500,
        "Shopping":  400,
        "Spa":       350,
    },
}
_DEFAULT_BUDGET_MULTIPLIER = {"Low": 0.9, "Medium": 1.0, "Luxury": 1.6}
_DEFAULT_SEASON_MULTIPLIER = {"Regular": 1.0, "Peak": 2.0, "Off-Peak": 0.8}


# ── Booking redirect link helpers (Aggregator Model) ──────────
def _flight_links(origin: str, dest: str, date: datetime.date) -> dict:
    d = date.strftime("%Y-%m-%d")
    o = origin.replace(" ", "+")
    de = dest.replace(" ", "+")
    return {
        "MakeMyTrip":  f"https://www.makemytrip.com/flights/international/search/?tripType=O&itinerary={o}-{de}-{d}&paxType=A-1_C-0_I-0&cabinClass=E",
        "Skyscanner":  f"https://www.skyscanner.net/transport/flights/{o[:3]}/{de[:3]}/{date.strftime('%y%m%d')}/",
        "Goibibo":     f"https://www.goibibo.com/flights/search/?source={o}&destination={de}&dateofdeparture={date.strftime('%Y%m%d')}&seating=E&adults=1&children=0&infants=0&counter=0",
        "Kayak":       f"https://www.kayak.com/flights/{o}-{de}/{d}",
    }

def _hotel_links(city: str) -> dict:
    c = city.replace(" ", "+")
    slug = city.lower().replace(" ", "-")
    return {
        "Booking.com": f"https://www.booking.com/searchresults.html?ss={c}",
        "Agoda":       f"https://www.agoda.com/search?city={c}",
        "Airbnb":      f"https://www.airbnb.com/s/{slug}/homes",
        "MakeMyTrip":  f"https://www.makemytrip.com/hotels/{slug}-hotels.html",
    }


# ── Trip cost calculator ──────────────────────────────────────
def compute_trip_cost(
    trip: dict,
    BASE_COSTS: dict | None = None,
    BUDGET_MULTIPLIER: dict | None = None,
    SEASON_MULTIPLIER: dict | None = None,
) -> dict:
    """
    Compute a detailed trip cost estimate.
    Supports single-arg call: compute_trip_cost(trip)
    """
    if BASE_COSTS is None:
        BASE_COSTS = _DEFAULT_BASE_COSTS
    if BUDGET_MULTIPLIER is None:
        BUDGET_MULTIPLIER = _DEFAULT_BUDGET_MULTIPLIER
    if SEASON_MULTIPLIER is None:
        SEASON_MULTIPLIER = _DEFAULT_SEASON_MULTIPLIER

    # Date handling
    try:
        start = trip.get("start_date", datetime.date.today())
        end   = trip.get("return_date", start + datetime.timedelta(days=1))
        if isinstance(start, str):
            start = datetime.date.fromisoformat(start)
        if isinstance(end, str):
            end = datetime.date.fromisoformat(end)
        days = max((end - start).days, 1)
    except Exception:
        days = int(trip.get("days", 1)) or 1

    travelers  = max(int(trip.get("travelers", 1)), 1)
    transport  = trip.get("transport", "Flight")
    budget     = trip.get("budget", "Medium")
    season     = trip.get("season", "Regular")
    extras_lst = trip.get("extras", [])

    transport_cost = BASE_COSTS["transport"].get(transport, 3500) * travelers
    hotel_cost     = BASE_COSTS["hotel_per_night"].get(budget, 1500) * days
    activity_cost  = BASE_COSTS["activities_per_day"] * days * travelers
    extras_cost    = sum(BASE_COSTS["extras"].get(e, 0) for e in extras_lst) * travelers

    subtotal = transport_cost + hotel_cost + activity_cost + extras_cost
    bm       = BUDGET_MULTIPLIER.get(budget, 1.0)
    sm       = SEASON_MULTIPLIER.get(season, 1.0)
    total    = subtotal * bm * sm

    return {
        "transport":  int(transport_cost),
        "hotel":      int(hotel_cost),
        "activities": int(activity_cost),
        "extras":     int(extras_cost),
        "subtotal":   int(subtotal),
        "total":      int(total),
        "per_day":    int(total / days),
        "per_person": int(total / travelers),
        "days":       days,
        "travelers":  travelers,
        "budget_mult": bm,
        "season_mult": sm,
    }


# ── Location data ─────────────────────────────────────────────
INTERNATIONAL_COUNTRIES = {
    "India":        ["Delhi", "Punjab", "Haryana", "Uttar Pradesh", "Uttarakhand",
                     "Maharashtra", "Gujarat", "Rajasthan", "Tamil Nadu", "Karnataka",
                     "Kerala", "Telangana", "Andhra Pradesh", "West Bengal", "Bihar",
                     "Odisha", "Assam", "Goa", "Himachal Pradesh"],
    "USA":          ["New York", "Los Angeles", "Chicago", "Miami", "San Francisco", "Las Vegas"],
    "UK":           ["London", "Manchester", "Edinburgh", "Liverpool", "Birmingham"],
    "Australia":    ["Sydney", "Melbourne", "Brisbane", "Perth", "Adelaide"],
    "France":       ["Paris", "Lyon", "Nice", "Marseille", "Bordeaux"],
    "Japan":        ["Tokyo", "Osaka", "Kyoto", "Hiroshima", "Sapporo"],
    "Germany":      ["Berlin", "Munich", "Frankfurt", "Hamburg", "Cologne"],
    "Canada":       ["Toronto", "Vancouver", "Montreal", "Ottawa", "Calgary"],
    "Italy":        ["Rome", "Venice", "Milan", "Florence", "Naples"],
    "Singapore":    ["Singapore City"],
    "UAE":          ["Dubai", "Abu Dhabi", "Sharjah"],
    "Thailand":     ["Bangkok", "Phuket", "Chiang Mai", "Pattaya"],
    "Spain":        ["Madrid", "Barcelona", "Valencia", "Seville"],
    "Switzerland":  ["Zurich", "Geneva", "Lucerne", "Bern"],
    "Netherlands":  ["Amsterdam", "Rotterdam", "Utrecht"],
    "Greece":       ["Athens", "Santorini", "Mykonos"],
    "Turkey":       ["Istanbul", "Ankara", "Antalya"],
    "China":        ["Beijing", "Shanghai", "Guangzhou"],
    "South Korea":  ["Seoul", "Busan", "Incheon"],
    "Malaysia":     ["Kuala Lumpur", "Penang", "Langkawi"],
    "Indonesia":    ["Bali", "Jakarta", "Yogyakarta"],
    "Vietnam":      ["Hanoi", "Ho Chi Minh City", "Da Nang"],
    "Sri Lanka":    ["Colombo", "Kandy", "Galle"],
    "Nepal":        ["Kathmandu", "Pokhara"],
    "Maldives":     ["Male"],
    "Russia":       ["Moscow", "Saint Petersburg"],
    "Brazil":       ["Rio de Janeiro", "Sao Paulo"],
    "Mexico":       ["Cancun", "Mexico City"],
    "South Africa": ["Cape Town", "Johannesburg", "Durban"],
    "Egypt":        ["Cairo", "Alexandria", "Luxor"],
    "Morocco":      ["Marrakech", "Casablanca"],
}


# ── CSS ───────────────────────────────────────────────────────
def _inject_dashboard_css():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Syne:wght@600;700;800&family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700;1,9..40,400&display=swap');
    [data-testid="stAppViewContainer"] { overflow-y:auto !important; }
    .block-container { padding:1.8rem 1.6rem 5rem !important; max-width:1180px !important; }

    /* Dashboard stat cards */
    .dash-stat {
        background:rgba(255,255,255,0.04);
        backdrop-filter:blur(16px); -webkit-backdrop-filter:blur(16px);
        border:1px solid rgba(255,255,255,0.07);
        border-radius:14px; padding:14px 16px;
        box-shadow:0 4px 20px rgba(0,0,0,0.22);
        transition:transform .15s, box-shadow .15s;
    }
    .dash-stat:hover { transform:translateY(-2px); box-shadow:0 8px 28px rgba(0,0,0,0.32); }
    .dash-stat-val { font-family:'Syne',sans-serif; font-size:1.26rem; font-weight:800; line-height:1.1; }
    .dash-stat-lbl { font-size:0.67rem; font-weight:600; text-transform:uppercase; letter-spacing:.5px; color:rgba(148,163,184,0.56); margin-top:3px; }

    /* Colored transport/hotel cards */
    .stat-card { border-radius:12px; padding:12px 15px; margin-bottom:6px; box-shadow:0 3px 14px rgba(0,0,0,0.28); }
    .stat-card.transport { background:linear-gradient(135deg,#047857,#10B981); }
    .stat-card.hotel     { background:linear-gradient(135deg,#1D4ED8,#3B82F6); }
    .stat-card.activity  { background:linear-gradient(135deg,#B91C1C,#EF4444); }
    .stat-card.total     { background:linear-gradient(135deg,#D97706,#F59E0B); }
    .stat-value { font-size:1.30rem; font-weight:800; color:#fff; font-family:'Syne',sans-serif; }
    .stat-label { font-size:0.68rem; font-weight:700; color:rgba(255,255,255,0.78); text-transform:uppercase; letter-spacing:.5px; }

    /* Sidebar inputs */
    .stTextInput input, div[data-baseweb="input"] input {
        background:#0A1628 !important; border:1.5px solid rgba(148,163,184,0.18) !important;
        border-radius:10px !important; color:#E2E8F0 !important;
        -webkit-text-fill-color:#E2E8F0 !important; caret-color:#F59E0B !important;
        padding:9px 13px !important; font-size:.88rem !important;
        transition:border-color .18s, box-shadow .18s !important;
    }
    .stTextInput input:focus, div[data-baseweb="input"] input:focus {
        border-color:#F59E0B !important; box-shadow:0 0 0 3px rgba(245,158,11,0.14) !important; background:#0D1E3A !important;
    }
    .stSelectbox > div > div, .stMultiSelect > div > div {
        background:#0A1628 !important; border:1.5px solid rgba(148,163,184,0.18) !important;
        border-radius:10px !important; color:#E2E8F0 !important;
    }
    .stNumberInput input, .stDateInput input {
        background:#0A1628 !important; color:#E2E8F0 !important;
        -webkit-text-fill-color:#E2E8F0 !important;
        border:1.5px solid rgba(148,163,184,0.18) !important;
    }
    .stTextInput label, .stSelectbox label, .stNumberInput label,
    .stDateInput label, .stRadio label, .stSlider label, .stMultiSelect label {
        color:rgba(148,163,184,0.65) !important; font-size:.69rem !important;
        font-weight:700 !important; text-transform:uppercase !important; letter-spacing:.65px !important;
    }
    .stButton > button {
        background:linear-gradient(135deg,#F59E0B,#FCD34D) !important;
        color:#0A0500 !important; border:none !important; border-radius:10px !important;
        padding:10px 18px !important; font-weight:700 !important; font-size:.87rem !important;
        transition:transform .13s, box-shadow .13s !important;
        box-shadow:0 3px 14px rgba(245,158,11,.32) !important;
    }
    .stButton > button:hover { transform:translateY(-2px) !important; box-shadow:0 7px 22px rgba(245,158,11,.46) !important; }
    [data-testid="stMetricLabel"] { color:rgba(148,163,184,.65) !important; font-size:.68rem !important; font-weight:600 !important; text-transform:uppercase !important; }
    [data-testid="stMetricValue"] { color:#F1F5F9 !important; font-size:1.22rem !important; font-weight:800 !important; font-family:'Syne',sans-serif !important; }
    [data-testid="stLinkButton"] a {
        background:rgba(255,255,255,.055) !important; border:1px solid rgba(255,255,255,.10) !important;
        border-radius:9px !important; color:#CBD5E1 !important;
        font-size:.80rem !important; font-weight:600 !important; padding:7px 12px !important;
        text-decoration:none !important; display:inline-flex !important; align-items:center !important; gap:5px !important;
        transition:all .13s !important;
    }
    [data-testid="stLinkButton"] a:hover { background:rgba(245,158,11,.12) !important; border-color:rgba(245,158,11,.38) !important; color:#FCD34D !important; }
    </style>
    """, unsafe_allow_html=True)

# ── MAIN DASHBOARD ────────────────────────────────────────────
def cost_dashboard(user: dict):
    try:
        import theme
        theme.apply_global_theme()
    except ImportError:
        pass
    _inject_dashboard_css()

    st.markdown(
        '<div style="padding:6px 0 8px 0;">' +
        '<h1 style="margin:0;font-size:1.40rem;font-weight:800;color:#F8FAFC;">💰 Trip Planner & Dashboard</h1>' +
        f'<p style="color:rgba(255,255,255,0.55);font-size:0.76rem;margin:2px 0 0 0;">Logged in as {user.get("full_name","Traveller")} · Aggregator Model — Compare & Book</p>' +
        '</div>',
        unsafe_allow_html=True,
    )

    # Session defaults
    for k, v in [("trip", {}), ("costs", {}), ("spoken", False)]:
        if k not in st.session_state:
            st.session_state[k] = v

    BASE_COSTS        = _DEFAULT_BASE_COSTS
    BUDGET_MULTIPLIER = _DEFAULT_BUDGET_MULTIPLIER
    SEASON_MULTIPLIER = _DEFAULT_SEASON_MULTIPLIER

    # ── Sidebar inputs ──────────────────────────────────────
    with st.sidebar:
        st.header("✍️ Plan Your Trip")

        origin_country = st.selectbox("Origin Country", list(INTERNATIONAL_COUNTRIES.keys()), key="fh_orig_country")
        origin_city    = st.selectbox("Origin City / State", INTERNATIONAL_COUNTRIES[origin_country], key="fh_orig_city")

        dest_country   = st.selectbox("Destination Country", list(INTERNATIONAL_COUNTRIES.keys()), key="fh_dest_country")
        dest_city      = st.selectbox("Destination City / State", INTERNATIONAL_COUNTRIES[dest_country], key="fh_dest_city")

        start_date  = st.date_input("Departure Date", datetime.date.today(), key="fh_start")
        return_date = st.date_input("Return Date", datetime.date.today() + datetime.timedelta(days=3), key="fh_return")
        travelers   = st.number_input("Number of Travelers", 1, 20, 2, key="fh_travelers")

        transport_opts = ["Bus", "Train", "Flight"] if origin_country == dest_country else ["Flight"]
        transport  = st.selectbox("Transport Type", transport_opts, key="fh_transport")

        budget  = st.selectbox("Budget Level", ["Low", "Medium", "Luxury"], index=1, key="fh_budget")
        season  = st.selectbox("Season", ["Regular", "Peak", "Off-Peak"], key="fh_season")
        extras  = st.multiselect("Optional Extras", list(BASE_COSTS["extras"].keys()), key="fh_extras")

        st.markdown("---")
        if st.button("🔄 Reset Planner", key="fh_reset"):
            for k in ["trip", "costs", "spoken", "itinerary_generated", "itinerary_data"]:
                st.session_state.pop(k, None)
            st.rerun()

    # ── Validation ──────────────────────────────────────────
    errors = []
    if origin_city.lower() == dest_city.lower() and origin_country == dest_country:
        errors.append("Origin and destination cannot be the same.")
    if return_date <= start_date:
        errors.append("Return date must be after departure date.")
    if travelers <= 0:
        errors.append("At least one traveler is required.")

    if errors:
        for e in errors:
            st.error(f"❌ {e}")
        return

    # ── Build trip dict ──────────────────────────────────────
    trip = {
        "origin_country":   origin_country,
        "origin_city":      origin_city,
        "dest_country":     dest_country,
        "destination_city": dest_city,
        "start_date":       start_date,
        "return_date":      return_date,
        "travelers":        travelers,
        "transport":        transport,
        "budget":           budget,
        "season":           season,
        "extras":           extras,
    }

    costs = compute_trip_cost(trip, BASE_COSTS, BUDGET_MULTIPLIER, SEASON_MULTIPLIER)
    st.session_state.trip  = trip
    st.session_state.costs = costs

    # ── Trip summary header ──────────────────────────────────
    st.markdown('<div class="dash-block">', unsafe_allow_html=True)
    st.subheader("🧾 Trip Summary")
    days = costs["days"]
    st.info(
        f"**{origin_city}** → **{dest_city}** | "
        f"📅 {days} day{'s' if days > 1 else ''} | "
        f"👥 {travelers} traveler{'s' if travelers > 1 else ''} | "
        f"💳 {budget} | 🗓️ {season}"
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("💰 Total", f"₹{costs['total']:,}")
    c2.metric("📆 Per Day", f"₹{costs['per_day']:,}")
    c3.metric("👤 Per Person", f"₹{costs['per_person']:,}")
    c4.metric("🎁 Extras", f"₹{costs['extras']:,}")
    st.markdown('</div>', unsafe_allow_html=True)

    # Speak total once
    if not st.session_state.spoken:
        speak(f"Total trip cost is {costs['total']} rupees for {travelers} traveler{'s' if travelers > 1 else ''}")
        st.session_state.spoken = True

    # ── Cost breakdown chart ─────────────────────────────────
    st.markdown('<div class="dash-block">', unsafe_allow_html=True)
    st.subheader("📊 Cost Breakdown")
    df = pd.DataFrame({
        "Category": ["✈️ Transport", "🏨 Hotel", "🎯 Activities", "🎁 Extras"],
        "Cost (₹)": [costs["transport"], costs["hotel"], costs["activities"], costs["extras"]],
    })
    chart = (
        alt.Chart(df)
        .mark_bar(cornerRadiusTopLeft=6, cornerRadiusTopRight=6)
        .encode(
            x=alt.X("Category", sort="-y", axis=alt.Axis(labelColor="#cbd5e1", titleColor="#94a3b8")),
            y=alt.Y("Cost (₹)", axis=alt.Axis(labelColor="#cbd5e1", titleColor="#94a3b8")),
            color=alt.Color("Category", legend=None,
                            scale=alt.Scale(range=["#F6A81A", "#3b82f6", "#10b981", "#ef4444"])),
            tooltip=["Category", "Cost (₹)"],
        )
        .properties(height=260)
        .configure_view(strokeOpacity=0)
        .configure(background="transparent")
    )
    st.altair_chart(chart, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # ── Booking platform links (Aggregator Model) ────────────
    st.markdown('<div class="dash-block">', unsafe_allow_html=True)
    st.subheader("✈️ Book Your Trip")
    st.caption("We compare options — click to book on trusted platforms")

    flight_links = _flight_links(origin_city, dest_city, start_date)
    hotel_links  = _hotel_links(dest_city)

    tab_flight, tab_hotel = st.tabs(["✈️ Flights", "🏨 Hotels"])

    with tab_flight:
        st.markdown(
            f"**Estimated Flight Cost:** ₹{costs['transport']:,} for {travelers} traveler{'s' if travelers > 1 else ''}"
        )
        st.caption("Prices are estimates. Click to see live prices on booking platforms.")
        cols = st.columns(len(flight_links))
        for i, (label, url) in enumerate(flight_links.items()):
            with cols[i]:
                st.link_button(f"🔗 {label}", url, use_container_width=True)

    with tab_hotel:
        st.markdown(
            f"**Estimated Hotel Cost:** ₹{costs['hotel']:,} for {days} night{'s' if days > 1 else ''}"
        )
        st.caption("Prices are estimates. Click to see live availability.")
        cols = st.columns(min(len(hotel_links), 4))
        for i, (label, url) in enumerate(hotel_links.items()):
            with cols[i % 4]:
                st.link_button(f"🔗 {label}", url, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # ── Trip overview table ──────────────────────────────────
    st.markdown('<div class="dash-block">', unsafe_allow_html=True)
    st.subheader("📌 Full Trip Overview")
    overview = pd.DataFrame([{
        "Origin":          origin_city,
        "Destination":     dest_city,
        "Days":            days,
        "Travelers":       travelers,
        "Transport":       transport,
        "Budget":          budget,
        "Season":          season,
        "Total (₹)":       f"₹{costs['total']:,}",
        "Per Person (₹)":  f"₹{costs['per_person']:,}",
        "Per Day (₹)":     f"₹{costs['per_day']:,}",
    }])
    st.dataframe(overview, use_container_width=True, hide_index=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # ── Quick actions ────────────────────────────────────────
    st.markdown("---")
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        if st.button("🧳 Plan Itinerary", key="fh_go_itin", use_container_width=True):
            st.session_state.sidebar_page = "Itinerary"
            st.rerun()
    with col_b:
        if st.button("🗺️ Explore Destination", key="fh_go_explore", use_container_width=True):
            st.session_state.sidebar_page = "Explorer"
            st.rerun()
    with col_c:
        if st.button("🏠 Back to Home", key="fh_go_home", use_container_width=True):
            st.session_state.sidebar_page = "Home"
            st.rerun()

    st.caption("💡 Smart Atlas uses an Aggregator + Redirect model. We never process payments or store booking data.")


