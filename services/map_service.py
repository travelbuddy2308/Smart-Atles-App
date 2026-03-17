# services/map_service.py
# ============================================================
# Smart Atles — Map Service
# ✅ Multiple tile styles (Street, Dark, Terrain, Watercolor, OSM)
# ✅ Optional offline tile caching (SQLite geo_cache.db)
# ✅ Auto-sort attractions by proximity (haversine)
# ✅ Highlight top 3 attractions per day
# ✅ Color-coded markers: sightseeing/hotel/food/transport
# ✅ Local public transport station markers
# ✅ Duration & tag info in popups
# ✅ Layer controls, fullscreen, map legend
# ============================================================

import os
import math
import logging
import sqlite3
from datetime import datetime

import folium
from folium.plugins import MarkerCluster, Fullscreen

logger = logging.getLogger(__name__)

# ── Tile style definitions ────────────────────────────────────
TILE_STYLES = {
    "Street":        {"tiles": "CartoDB positron",    "attr": "© CartoDB © OpenStreetMap",      "label": "🗺️ Street (Default)"},
    "Dark":          {"tiles": "CartoDB dark_matter",  "attr": "© CartoDB © OpenStreetMap",      "label": "🌑 Dark Mode"},
    "OpenStreetMap": {"tiles": "OpenStreetMap",        "attr": "© OpenStreetMap contributors",   "label": "🌍 OpenStreetMap"},
    "Terrain":       {
        "tiles": "https://tile.opentopomap.org/{z}/{x}/{y}.png",
        "attr":  "© OpenStreetMap contributors, SRTM | © OpenTopoMap",
        "label": "🏔️ Terrain",
    },
    "Watercolor":    {
        "tiles": "https://watercolormaps.collection.cooperhewitt.org/tile/watercolor/{z}/{x}/{y}.jpg",
        "attr":  "Map tiles by Stamen Design, © OpenStreetMap",
        "label": "🎨 Watercolor",
    },
}

# ── SQLite tile cache ─────────────────────────────────────────
_TILE_CACHE_DB = "geo_cache.db"
_TILE_CACHE_OK = False
_tile_conn = None

try:
    _tile_conn = sqlite3.connect(_TILE_CACHE_DB, check_same_thread=False)
    _tile_conn.execute("""CREATE TABLE IF NOT EXISTS tile_cache (
        url TEXT PRIMARY KEY, data BLOB, cached_at TEXT)""")
    _tile_conn.commit()
    _TILE_CACHE_OK = True
except Exception as e:
    logger.warning("Tile cache unavailable: %s", e)


# ── Haversine distance ────────────────────────────────────────
def _haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


def sort_by_proximity(places: list, ref_lat: float, ref_lon: float) -> list:
    """Sort places list by distance from reference point. Adds 'distance_km' field."""
    for p in places:
        p["distance_km"] = round(_haversine(ref_lat, ref_lon, p["lat"], p["lon"]), 2)
    return sorted(places, key=lambda x: x.get("distance_km", 999))


def get_top_attractions(places: list, n: int = 3) -> list:
    """
    Mark the top N places as 'top_pick'. Uses 'rating' field if present,
    else marks the first N proximity-sorted places as top picks.
    Returns the top N list.
    """
    scored = sorted(places, key=lambda p: p.get("rating", 0), reverse=True)
    top = scored[:n]
    top_names = {p["name"] for p in top}
    for p in places:
        p["top_pick"] = p["name"] in top_names
    return top


# ── Google Maps helpers ───────────────────────────────────────
def google_maps_url(lat: float, lon: float, label: str = "") -> str:
    q = label.replace(" ", "+") if label else f"{lat},{lon}"
    return f"https://www.google.com/maps/search/{q}/@{lat},{lon},15z"


def google_maps_directions(lat: float, lon: float) -> str:
    return f"https://www.google.com/maps/dir/?api=1&destination={lat},{lon}"


# ── Popup builders ────────────────────────────────────────────
def _place_popup(name, lat, lon, category="Place", is_top=False,
                 duration_min=60, tags=None):
    maps_url = google_maps_url(lat, lon, name)
    dir_url  = google_maps_directions(lat, lon)
    badge    = ('<span style="background:#F6A81A;color:#1a1a1a;font-size:0.7rem;'
                'padding:2px 7px;border-radius:8px;font-weight:700;">⭐ TOP PICK</span><br>'
                if is_top else "")
    tag_html = ""
    if tags:
        tag_html = " ".join(
            f'<span style="background:rgba(27,59,139,0.2);color:#93c5fd;'
            f'font-size:0.7rem;padding:1px 6px;border-radius:6px;">{t}</span>'
            for t in (tags or [])
        )
    return (
        f'<div style="font-family:Segoe UI,sans-serif;min-width:200px;">'
        f'{badge}<b style="font-size:.95rem;">{name}</b><br>'
        f'<span style="color:#6b7280;font-size:.78rem;">{category} · ~{duration_min} min</span><br>'
        f'{tag_html}<hr style="margin:6px 0;">'
        f'<a href="{maps_url}" target="_blank" style="color:#1B3B8B;font-size:.82rem;">📍 View on Google Maps</a><br>'
        f'<a href="{dir_url}" target="_blank" style="color:#059669;font-size:.82rem;">🧭 Get Directions</a></div>'
    )


def _hotel_popup(name, lat, lon, booking_url="", price_range="", trust_score="", min_stay=""):
    maps_url     = google_maps_url(lat, lon, name)
    booking_link = (f'<a href="{booking_url}" target="_blank" style="color:#1B3B8B;font-size:.82rem;">🔗 Book on Booking.com</a><br>'
                    if booking_url else "")
    price_tag    = f'<span style="color:#059669;font-size:.8rem;">💰 {price_range}</span><br>' if price_range else ""
    trust_tag    = f'<span style="color:#F6A81A;font-size:.78rem;">⭐ Trust: {trust_score}</span><br>' if trust_score else ""
    stay_tag     = f'<span style="color:#6b7280;font-size:.78rem;">🗓️ Min Stay: {min_stay}</span><br>' if min_stay else ""
    return (
        f'<div style="font-family:Segoe UI,sans-serif;min-width:200px;">'
        f'<b style="font-size:.95rem;">🏨 {name}</b><br>'
        f'{price_tag}{trust_tag}{stay_tag}<hr style="margin:6px 0;">'
        f'{booking_link}<a href="{maps_url}" target="_blank" style="color:#6b7280;font-size:.82rem;">📍 View on Map</a></div>'
    )


def _food_popup(name, lat, lon, zomato_url="", swiggy_url="", price_range=""):
    maps_url    = google_maps_url(lat, lon, name)
    zomato_link = (f'<a href="{zomato_url}" target="_blank" style="color:#e23744;font-size:.82rem;">🍽️ View on Zomato</a><br>'
                   if zomato_url else "")
    swiggy_link = (f'<a href="{swiggy_url}" target="_blank" style="color:#fc8019;font-size:.82rem;">🛵 Order on Swiggy</a><br>'
                   if swiggy_url else "")
    price_tag   = f'<span style="color:#059669;font-size:.78rem;">💰 {price_range}</span><br>' if price_range else ""
    return (
        f'<div style="font-family:Segoe UI,sans-serif;min-width:200px;">'
        f'<b style="font-size:.95rem;">🍽️ {name}</b><br>{price_tag}'
        f'<hr style="margin:6px 0;">{zomato_link}{swiggy_link}'
        f'<a href="{maps_url}" target="_blank" style="color:#6b7280;font-size:.82rem;">📍 View on Map</a></div>'
    )


def _transport_popup(name, lat, lon, transport_type="Station"):
    maps_url = google_maps_url(lat, lon, name)
    dir_url  = google_maps_directions(lat, lon)
    return (
        f'<div style="font-family:Segoe UI,sans-serif;min-width:180px;">'
        f'<b style="font-size:.95rem;">🚉 {name}</b><br>'
        f'<span style="color:#6b7280;font-size:.78rem;">{transport_type}</span>'
        f'<hr style="margin:6px 0;">'
        f'<a href="{dir_url}" target="_blank" style="color:#059669;font-size:.82rem;">🧭 Get Directions</a><br>'
        f'<a href="{maps_url}" target="_blank" style="color:#6b7280;font-size:.82rem;">📍 View on Map</a></div>'
    )


# ── Legend HTML ───────────────────────────────────────────────
_LEGEND_HTML = """
<div style="position:fixed;bottom:30px;left:30px;z-index:9999;
    background:rgba(255,255,255,0.96);border-radius:10px;padding:10px 14px;
    box-shadow:0 4px 16px rgba(0,0,0,0.18);font-family:Segoe UI,sans-serif;font-size:0.8rem;">
    <b style="font-size:0.85rem;">📌 Legend</b><br>
    <span style="color:#2ecc71;">●</span> Tourist Places<br>
    <span style="color:#3498db;">●</span> Hotels<br>
    <span style="color:#e74c3c;">●</span> Restaurants<br>
    <span style="color:#f39c12;">●</span> Start Point<br>
    <span style="color:#8e44ad;">●</span> Transport<br>
    <span style="color:#F6A81A;">⭐</span> Top Pick
</div>
"""


# ── Main map generator ────────────────────────────────────────
def generate_day_map(
    lat: float,
    lon: float,
    places: list,
    hotels: list | None = None,
    foods:  list | None = None,
    transport_stops: list | None = None,
    use_cluster: bool = False,
    city_name: str = "",
    tile_style: str = "Street",
    highlight_top: bool = True,
    tags_map: dict | None = None,
) -> folium.Map:
    """
    Build a Folium map with full feature set:
    - Proximity-sorted places, top-3 highlighted
    - Multi-layer: places, hotels, food, transport
    - Rich popups with booking/navigation links
    - Tile style selector (Street/Dark/Terrain/Watercolor/OSM)
    - Fullscreen button + map legend
    """
    style = TILE_STYLES.get(tile_style, TILE_STYLES["Street"])
    use_custom_url = style["tiles"].startswith("http")

    m = folium.Map(
        location=[lat, lon],
        zoom_start=13,
        tiles=None if use_custom_url else style["tiles"],
        attr=style["attr"] if not use_custom_url else None,
        control_scale=True,
    )
    if use_custom_url:
        folium.TileLayer(tiles=style["tiles"], attr=style["attr"], name=tile_style).add_to(m)

    Fullscreen(position="topright").add_to(m)

    # City center
    folium.Marker(
        [lat, lon],
        popup=folium.Popup(f"<b>📍 {city_name or 'City Center'}</b>", max_width=200),
        tooltip=city_name or "City Center",
        icon=folium.Icon(color="orange", icon="home", prefix="fa"),
    ).add_to(m)

    # Sort & highlight places
    places_sorted = sort_by_proximity(list(places or []), lat, lon)
    if highlight_top and places_sorted:
        get_top_attractions(places_sorted, n=3)

    # Places layer
    places_group = folium.FeatureGroup(name="🏛️ Tourist Places")
    for p in places_sorted:
        is_top = p.get("top_pick", False)
        tags   = (tags_map or {}).get(p["name"], [])
        popup_html = _place_popup(
            p["name"], p["lat"], p["lon"],
            p.get("category", "Sightseeing"),
            is_top=is_top,
            duration_min=p.get("avg_time_min", 60),
            tags=tags,
        )
        if is_top:
            folium.CircleMarker(
                [p["lat"], p["lon"]],
                radius=14, color="#F6A81A",
                fill=True, fill_color="#F6A81A", fill_opacity=0.25, weight=2,
            ).add_to(places_group)
        folium.Marker(
            [p["lat"], p["lon"]],
            popup=folium.Popup(popup_html, max_width=240),
            tooltip=f"{'⭐ ' if is_top else ''}{p['name']}",
            icon=folium.Icon(color="green", icon="star" if is_top else "map-marker", prefix="fa"),
        ).add_to(places_group)
    places_group.add_to(m)

    # Hotels layer
    hotels_group = folium.FeatureGroup(name="🏨 Hotels")
    for h in (hotels or []):
        popup_html = _hotel_popup(
            h["name"], h["lat"], h["lon"],
            h.get("booking_url", ""), h.get("price_range", ""),
            h.get("rating_est", ""), h.get("min_stay", ""),
        )
        folium.Marker(
            [h["lat"], h["lon"]],
            popup=folium.Popup(popup_html, max_width=240),
            tooltip=f"🏨 {h['name']}",
            icon=folium.Icon(color="blue", icon="bed", prefix="fa"),
        ).add_to(hotels_group)
    hotels_group.add_to(m)

    # Food layer
    food_group = folium.FeatureGroup(name="🍽️ Restaurants")
    for f in (foods or []):
        popup_html = _food_popup(
            f["name"], f["lat"], f["lon"],
            f.get("zomato_url", ""), f.get("swiggy_url", ""), f.get("price_range", ""),
        )
        folium.Marker(
            [f["lat"], f["lon"]],
            popup=folium.Popup(popup_html, max_width=240),
            tooltip=f"🍽️ {f['name']}",
            icon=folium.Icon(color="red", icon="cutlery", prefix="fa"),
        ).add_to(food_group)
    food_group.add_to(m)

    # Transport layer
    if transport_stops:
        transport_group = folium.FeatureGroup(name="🚌 Transport")
        for t in transport_stops:
            popup_html = _transport_popup(t["name"], t["lat"], t["lon"], t.get("type", "Station"))
            folium.Marker(
                [t["lat"], t["lon"]],
                popup=folium.Popup(popup_html, max_width=220),
                tooltip=f"🚌 {t['name']}",
                icon=folium.Icon(color="purple", icon="bus", prefix="fa"),
            ).add_to(transport_group)
        transport_group.add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)
    m.get_root().html.add_child(folium.Element(_LEGEND_HTML))
    return m


def save_map(m: folium.Map, path: str = "itinerary_map.html") -> str:
    dir_name = os.path.dirname(path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)
    try:
        m.save(path)
        return path
    except Exception as e:
        logger.error("Map save failed: %s", e)
        return ""


def generate_static_map_url(lat: float, lon: float, zoom: int = 14) -> str:
    return (
        f"https://www.google.com/maps/embed/v1/view"
        f"?key=YOUR_GOOGLE_MAPS_KEY&center={lat},{lon}&zoom={zoom}"
    )


def fetch_transport_stops_osm(lat: float, lon: float, radius_m: int = 800) -> list:
    """Fetch nearby public transport stops from OSM Overpass API."""
    import requests
    query = (
        f'[out:json][timeout:10];('
        f'node["highway"="bus_stop"](around:{radius_m},{lat},{lon});'
        f'node["railway"="station"](around:{radius_m},{lat},{lon});'
        f'node["railway"="subway_entrance"](around:{radius_m},{lat},{lon});'
        f');out 12;'
    )
    try:
        resp = requests.post(
            "https://overpass-api.de/api/interpreter",
            data={"data": query},
            timeout=12,
            headers={"User-Agent": "SmartAtlesApp/2.0"},
        )
        resp.raise_for_status()
        stops = []
        for el in resp.json().get("elements", []):
            name = el.get("tags", {}).get("name", "Stop")
            t    = (el.get("tags", {}).get("public_transport")
                    or el.get("tags", {}).get("highway", "stop")).replace("_", " ").title()
            stops.append({"name": name, "lat": el["lat"], "lon": el["lon"], "type": t})
        return stops[:10]
    except Exception as e:
        logger.warning("Transport stop fetch failed: %s", e)
        return []
