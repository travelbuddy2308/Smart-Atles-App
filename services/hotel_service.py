# services/hotel_service.py
# ============================================================
# Smart Atles — Hotel Service
# Fetches nearby hotels via OSM + generates platform redirect
# links (Booking.com, Agoda, Airbnb, MakeMyTrip) — Aggregator model.
# ============================================================

import requests
import time
import logging

logger = logging.getLogger(__name__)

_USER_AGENT = "SmartAtlesApp/2.0 (travel-planner)"
_OSM_URL    = "https://nominatim.openstreetmap.org/search"
_TIMEOUT    = 10


# ── Platform redirect helpers ─────────────────────────────────
def booking_url(city: str) -> str:
    return f"https://www.booking.com/searchresults.html?ss={city.replace(' ', '+')}"

def agoda_url(city: str) -> str:
    return f"https://www.agoda.com/search?city={city.replace(' ', '+')}"

def airbnb_url(city: str) -> str:
    return f"https://www.airbnb.com/s/{city.replace(' ', '-')}/homes"

def makemytrip_url(city: str) -> str:
    return f"https://www.makemytrip.com/hotels/{city.lower().replace(' ', '-')}-hotels.html"

def google_hotels_url(city: str) -> str:
    return f"https://www.google.com/travel/hotels/{city.replace(' ', '+')}?hl=en"


# ── Price range estimator ─────────────────────────────────────
_PRICE_BANDS = {
    "hotel":      {"Budget": "₹800–₹2,000/night",  "Luxury": "₹4,000–₹12,000/night"},
    "hostel":     {"Budget": "₹300–₹800/night",     "Luxury": "₹800–₹2,000/night"},
    "motel":      {"Budget": "₹600–₹1,500/night",   "Luxury": "₹1,500–₹4,000/night"},
    "guest_house":{"Budget": "₹500–₹1,200/night",   "Luxury": "₹1,200–₹3,000/night"},
}

def estimate_price(place_type: str = "hotel") -> str:
    band = _PRICE_BANDS.get(place_type.lower(), _PRICE_BANDS["hotel"])
    return band["Budget"]


# ── Internal OSM fetch ────────────────────────────────────────
def _osm_fetch(query: str, lat: float, lon: float, limit: int) -> list:
    params = {
        "q":      query,
        "format": "json",
        "limit":  limit,
        "lat":    lat,
        "lon":    lon,
        "radius": 5000,
    }
    headers = {"User-Agent": _USER_AGENT}
    for attempt in range(2):
        try:
            resp = requests.get(_OSM_URL, params=params, headers=headers, timeout=_TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.Timeout:
            logger.warning("Hotel OSM timeout (attempt %d)", attempt + 1)
            time.sleep(0.5)
        except requests.exceptions.RequestException as e:
            logger.error("Hotel OSM request failed: %s", e)
            break
    return []


# ── Main public function ──────────────────────────────────────
def get_hotels_near(lat: float, lon: float, limit: int = 6, city: str = "") -> list[dict]:
    """
    Fetch nearby hotels around (lat, lon).

    Returns list of dicts:
        name, lat, lon, type, price_range,
        booking_url, agoda_url, airbnb_url, makemytrip_url, google_url
    """
    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        logger.warning("Invalid coordinates for hotel search.")
        return []

    raw = _osm_fetch("hotel", lat, lon, limit)
    hotels = []

    for item in raw:
        name = item.get("display_name", "Hotel").split(",")[0].strip()
        h_type = item.get("type", "hotel")

        hotels.append({
            "name":           name,
            "full_address":   item.get("display_name", name),
            "lat":            float(item.get("lat", lat)),
            "lon":            float(item.get("lon", lon)),
            "type":           h_type.replace("_", " ").title(),
            "price_range":    estimate_price(h_type),
            "rating_est":     "3–4 ⭐ (est.)",
            "booking_url":    booking_url(city or name),
            "agoda_url":      agoda_url(city or name),
            "airbnb_url":     airbnb_url(city or name),
            "makemytrip_url": makemytrip_url(city or name),
            "google_url":     google_hotels_url(city or name),
        })

    # Expand search to hostels/guest houses if needed
    if len(hotels) < limit:
        for q in ["hostel", "guest_house"]:
            extra = _osm_fetch(q, lat, lon, limit - len(hotels))
            for item in extra:
                name = item.get("display_name", q).split(",")[0].strip()
                hotels.append({
                    "name":           name,
                    "full_address":   item.get("display_name", name),
                    "lat":            float(item.get("lat", lat)),
                    "lon":            float(item.get("lon", lon)),
                    "type":           q.replace("_", " ").title(),
                    "price_range":    estimate_price(q),
                    "rating_est":     "2–3 ⭐ (est.)",
                    "booking_url":    booking_url(city or name),
                    "agoda_url":      agoda_url(city or name),
                    "airbnb_url":     airbnb_url(city or name),
                    "makemytrip_url": makemytrip_url(city or name),
                    "google_url":     google_hotels_url(city or name),
                })
            if len(hotels) >= limit:
                break

    return hotels[:limit]


def get_platform_links(city: str) -> dict:
    """Return booking platform links for a city."""
    return {
        "Booking.com":  booking_url(city),
        "Agoda":        agoda_url(city),
        "Airbnb":       airbnb_url(city),
        "MakeMyTrip":   makemytrip_url(city),
        "Google Hotels":google_hotels_url(city),
    }
