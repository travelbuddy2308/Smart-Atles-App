# services/weather_service.py
# ============================================================
# Smart Atles — Weather Service
# Fetches live weather from OpenWeatherMap API.
# Returns rich data including travel advice, clothing tips,
# and redirect links to trusted weather platforms.
# ============================================================

import requests
import logging
import time

import streamlit as st

logger = logging.getLogger(__name__)

_OWM_BASE = "https://api.openweathermap.org/data/2.5"
_TIMEOUT  = 10

# ── Weather emoji mapping ─────────────────────────────────────
_EMOJI_MAP = {
    "clear sky":           "☀️",
    "few clouds":          "🌤️",
    "scattered clouds":    "⛅",
    "broken clouds":       "☁️",
    "overcast clouds":     "☁️",
    "light rain":          "🌦️",
    "moderate rain":       "🌧️",
    "heavy rain":          "🌧️",
    "thunderstorm":        "⛈️",
    "snow":                "❄️",
    "light snow":          "🌨️",
    "mist":                "🌫️",
    "haze":                "🌫️",
    "fog":                 "🌫️",
    "drizzle":             "🌦️",
    "smoke":               "💨",
    "dust":                "💨",
    "sand":                "💨",
    "tornado":             "🌪️",
}

def _get_emoji(description: str) -> str:
    desc_lower = description.lower()
    for kw, emoji in _EMOJI_MAP.items():
        if kw in desc_lower:
            return emoji
    return "🌡️"


# ── Travel advice generator ───────────────────────────────────
def _travel_advice(temp: float, condition: str, humidity: int) -> dict:
    advice    = []
    outfit    = []
    packing   = []
    cond      = condition.lower()

    if "rain" in cond or "drizzle" in cond or "thunderstorm" in cond:
        advice.append("Carry an umbrella and waterproof footwear.")
        outfit   = ["Waterproof jacket", "Quick-dry pants"]
        packing  = ["Umbrella", "Raincoat", "Waterproof bag cover"]
    elif "snow" in cond:
        advice.append("Pack warm layers and waterproof boots.")
        outfit   = ["Thermal inner wear", "Heavy jacket", "Waterproof boots"]
        packing  = ["Gloves", "Beanie", "Hand warmers"]
    elif temp >= 35:
        advice.append("Extreme heat — stay hydrated and use sunscreen SPF 50+.")
        outfit   = ["Light cotton", "Hat or cap"]
        packing  = ["Sunscreen", "Water bottle", "Electrolyte sachets"]
    elif temp >= 28:
        advice.append("Warm weather — breathable fabrics recommended.")
        outfit   = ["Cotton shirt", "Light pants or shorts"]
        packing  = ["Sunglasses", "Sunscreen", "Water bottle"]
    elif temp < 5:
        advice.append("Very cold — heavy winter clothing is essential.")
        outfit   = ["Thermal layers", "Heavy coat", "Woollen socks"]
        packing  = ["Gloves", "Scarf", "Beanie", "Hand warmers"]
    elif temp < 15:
        advice.append("Cool weather — layered clothing works best.")
        outfit   = ["Light jacket", "Full sleeves", "Comfortable shoes"]
        packing  = ["Light scarf", "Extra layer"]
    else:
        advice.append("Great travel weather! Enjoy your trip.")
        outfit   = ["Casual wear", "Comfortable shoes"]
        packing  = ["Light jacket for evenings"]

    if humidity > 80:
        advice.append("High humidity — expect a sticky feel; choose breathable fabric.")
    elif humidity < 25:
        advice.append("Low humidity — keep a lip balm and moisturiser handy.")

    return {
        "advice":  " ".join(advice),
        "outfit":  outfit,
        "packing": packing,
    }


# ── Redirect links ────────────────────────────────────────────
def weather_platform_links(city: str) -> dict:
    city_enc = city.replace(" ", "+")
    return {
        "AccuWeather":   f"https://www.accuweather.com/en/search-locations?query={city_enc}",
        "Weather.com":   f"https://weather.com/weather/today/l/{city_enc}",
        "Windy":         f"https://www.windy.com/?{city_enc}",
        "TimeandDate":   f"https://www.timeanddate.com/weather/{city_enc.replace('+','-')}",
    }


# ── API key reader ────────────────────────────────────────────
def _api_key() -> str:
    """
    Try every known key location in secrets.toml.
    Supports both flat and nested secrets layout.
    """
    try:
        # 1. Top-level: OPENWEATHER_API_KEY = "..."
        key = st.secrets.get("OPENWEATHER_API_KEY", "")
        if key and key not in ("YOUR_OPENWEATHER_API_KEY", "PASTE_YOUR_OPENWEATHER_KEY_HERE", ""):
            return key
        # 2. Nested: [api] openweather_key = "..."
        key = st.secrets.get("api", {}).get("openweather_key", "")
        if key and key not in ("YOUR_OPENWEATHER_KEY", "YOUR_OPENWEATHER_API_KEY", "PASTE_YOUR_OPENWEATHER_KEY_HERE", ""):
            return key
        # 3. Nested: [api] key = "..."
        key = st.secrets.get("api", {}).get("key", "")
        if key and "YOUR" not in key:
            return key
        return ""
    except Exception:
        return ""


# ── Main public function ──────────────────────────────────────
def get_weather_by_city(city: str) -> dict | None:
    """
    Fetch current weather for a city.

    Returns dict:
        city, temp, feels_like, humidity, condition, emoji,
        wind_speed, wind_deg, visibility, pressure, lat, lon,
        advice, outfit, packing, platform_links

    Returns None on failure.
    """
    api_key = _api_key()
    if not api_key:
        logger.warning("OpenWeatherMap API key not configured.")
        return None

    city = city.strip()
    if not city:
        return None

    for attempt in range(2):
        try:
            resp = requests.get(
                f"{_OWM_BASE}/weather",
                params={"q": city, "units": "metric", "appid": api_key},
                timeout=_TIMEOUT,
            )
            if resp.status_code == 404:
                logger.warning("City not found: %s", city)
                return None
            resp.raise_for_status()
            data = resp.json()

            condition   = data["weather"][0]["description"]
            temp        = round(data["main"]["temp"], 1)
            feels_like  = round(data["main"]["feels_like"], 1)
            humidity    = data["main"]["humidity"]
            wind_speed  = data["wind"].get("speed", 0)
            wind_deg    = data["wind"].get("deg", 0)
            visibility  = data.get("visibility", 0) // 1000  # km
            pressure    = data["main"].get("pressure", 0)

            travel      = _travel_advice(temp, condition, humidity)

            return {
                "city":           city.title(),
                "temp":           temp,
                "feels_like":     feels_like,
                "humidity":       humidity,
                "condition":      condition.title(),
                "emoji":          _get_emoji(condition),
                "wind_speed":     wind_speed,
                "wind_deg":       wind_deg,
                "visibility_km":  visibility,
                "pressure_hpa":   pressure,
                "lat":            data["coord"]["lat"],
                "lon":            data["coord"]["lon"],
                "advice":         travel["advice"],
                "outfit":         travel["outfit"],
                "packing":        travel["packing"],
                "platform_links": weather_platform_links(city),
            }

        except requests.exceptions.Timeout:
            logger.warning("Weather API timeout (attempt %d)", attempt + 1)
            time.sleep(0.5)
        except requests.exceptions.RequestException as e:
            logger.error("Weather API error: %s", e)
            break

    return None


def get_forecast_url(city: str) -> str:
    """Return a direct 5-day forecast link for AccuWeather."""
    return f"https://www.accuweather.com/en/search-locations?query={city.replace(' ', '+')}"
