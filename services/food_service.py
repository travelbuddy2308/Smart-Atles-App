# services/food_service.py
# ============================================================
# Smart Atles — Food Service
# Fetches nearby restaurants via OpenStreetMap + generates
# platform redirect links (Zomato / Swiggy) — Aggregator model.
# ============================================================

import requests
import time
import logging
from functools import lru_cache

logger = logging.getLogger(__name__)

_USER_AGENT = "SmartAtlesApp/2.0 (travel-planner)"
_OSM_URL    = "https://nominatim.openstreetmap.org/search"
_TIMEOUT    = 10
_CACHE_TTL  = 3600  # 1 hour in seconds

# ── Platform redirect helpers (Aggregator Model) ──────────────
def zomato_search_url(city: str, query: str = "restaurants") -> str:
    city_slug = city.lower().replace(" ", "-")
    return f"https://www.zomato.com/{city_slug}/{query}"

def swiggy_search_url(city: str) -> str:
    return f"https://www.swiggy.com/restaurants?query={city.replace(' ', '+')}"

def google_food_url(name: str, city: str) -> str:
    q = f"{name}+{city}+restaurant".replace(" ", "+")
    return f"https://www.google.com/search?q={q}"

# ── Internal request helper ───────────────────────────────────
def _osm_search(query: str, lat: float, lon: float, limit: int) -> list:
    """Single OSM request with retry on transient failures."""
    params = {
        "q":      query,
        "format": "json",
        "limit":  limit,
        "lat":    lat,
        "lon":    lon,
        "radius": 4000,
    }
    headers = {"User-Agent": _USER_AGENT}
    for attempt in range(2):
        try:
            resp = requests.get(_OSM_URL, params=params, headers=headers, timeout=_TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.Timeout:
            logger.warning("OSM food request timed out (attempt %d)", attempt + 1)
            time.sleep(0.5)
        except requests.exceptions.RequestException as e:
            logger.error("OSM food request failed: %s", e)
            break
    return []


# ── Main public function ──────────────────────────────────────
def get_food_near(lat: float, lon: float, limit: int = 6, city: str = "") -> list[dict]:
    """
    Fetch nearby restaurants around (lat, lon).

    Returns a list of dicts:
        name, lat, lon, type, zomato_url, swiggy_url, google_url, price_range
    """
    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        logger.warning("Invalid coordinates: lat=%s, lon=%s", lat, lon)
        return []

    raw_data = _osm_search("restaurant", lat, lon, limit)

    food_list = []
    for item in raw_data:
        name = item.get("display_name", "Restaurant")
        # Shorten display_name to first meaningful part
        short_name = name.split(",")[0].strip() if "," in name else name
        item_lat   = float(item.get("lat", lat))
        item_lon   = float(item.get("lon", lon))
        item_type  = item.get("type", "restaurant").replace("_", " ").title()

        food_list.append({
            "name":         short_name,
            "full_address": name,
            "lat":          item_lat,
            "lon":          item_lon,
            "type":         item_type,
            "price_range":  "₹150–₹600 per person (est.)",
            "zomato_url":   zomato_search_url(city or short_name),
            "swiggy_url":   swiggy_search_url(city or short_name),
            "google_url":   google_food_url(short_name, city),
        })

    # Also add nearby cafes
    if len(food_list) < limit:
        cafe_data = _osm_search("cafe", lat, lon, limit - len(food_list))
        for item in cafe_data:
            name = item.get("display_name", "Cafe").split(",")[0].strip()
            food_list.append({
                "name":         name,
                "full_address": item.get("display_name", name),
                "lat":          float(item.get("lat", lat)),
                "lon":          float(item.get("lon", lon)),
                "type":         "Cafe",
                "price_range":  "₹80–₹300 per person (est.)",
                "zomato_url":   zomato_search_url(city or name),
                "swiggy_url":   swiggy_search_url(city or name),
                "google_url":   google_food_url(name, city),
            })

    return food_list[:limit]


def get_platform_links(city: str) -> dict:
    """Return top-level food delivery platform links for a city."""
    return {
        "Zomato":  zomato_search_url(city),
        "Swiggy":  swiggy_search_url(city),
        "Google":  f"https://www.google.com/search?q=best+restaurants+in+{city.replace(' ', '+')}",
    }
