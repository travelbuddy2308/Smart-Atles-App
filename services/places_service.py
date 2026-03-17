# services/places_service.py
# ============================================================
# Smart Atles — Places Service
# Geocodes a city and fetches tourism POIs via Geoapify API.
# Includes category filtering, caching, and smart fallbacks.
# ============================================================

import requests
import logging
import time
from functools import lru_cache

import streamlit as st

logger = logging.getLogger(__name__)

_TIMEOUT = 12
_GEOAPIFY_BASE = "https://api.geoapify.com"

# Category aliases for cleaner API calls
CATEGORY_MAP = {
    "tourism":      "tourism",
    "culture":      "entertainment.culture",
    "nature":       "natural",
    "food":         "catering",
    "shopping":     "commercial.shopping_mall",
    "religion":     "religion",
    "beach":        "beach",
    "adventure":    "leisure.park",
    "nightlife":    "entertainment",
}


def _api_key() -> str:
    """Read Geoapify API key from Streamlit secrets (safe read)."""
    try:
        return st.secrets["api"]["geoapify_key"]
    except Exception:
        logger.warning("Geoapify API key not found in secrets.toml")
        return ""


def _geocode_city(city: str, api_key: str) -> tuple[float, float] | tuple[None, None]:
    """Geocode a city name to (lat, lon). Returns (None, None) on failure."""
    try:
        resp = requests.get(
            f"{_GEOAPIFY_BASE}/v1/geocode/search",
            params={"text": city, "limit": 1, "apiKey": api_key},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        features = resp.json().get("features", [])
        if not features:
            return None, None
        lon, lat = features[0]["geometry"]["coordinates"]
        return float(lat), float(lon)
    except Exception as e:
        logger.error("Geocoding failed for '%s': %s", city, e)
        return None, None


def _fetch_pois(lat: float, lon: float, category: str,
                radius_m: int, limit: int, api_key: str) -> list[dict]:
    """Fetch POIs from Geoapify Places API."""
    try:
        resp = requests.get(
            f"{_GEOAPIFY_BASE}/v2/places",
            params={
                "categories": category,
                "filter":     f"circle:{lon},{lat},{radius_m}",
                "limit":      limit,
                "apiKey":     api_key,
            },
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json().get("features", [])
    except Exception as e:
        logger.error("POI fetch failed (category=%s): %s", category, e)
        return []


def _parse_feature(f: dict) -> dict | None:
    """Parse a Geoapify feature into a clean dict."""
    props = f.get("properties", {})
    name  = props.get("name", "").strip()
    if not name:
        return None
    return {
        "name":      name,
        "lat":       float(props.get("lat", 0)),
        "lon":       float(props.get("lon", 0)),
        "address":   props.get("formatted", ""),
        "category":  props.get("categories", [""])[0].split(".")[-1].replace("_", " ").title(),
        "wiki_url":  props.get("wiki_and_media", {}).get("wikipedia", ""),
        "website":   props.get("datasource", {}).get("url", ""),
        "distance":  props.get("distance", 0),
    }


def get_places_for_city(
    city: str,
    limit: int = 30,
    categories: list[str] | None = None,
    radius_m: int = 8000,
) -> list[dict]:
    """
    Geocode city → fetch tourism POIs within radius_m metres.

    Args:
        city:       City name (e.g. "Goa")
        limit:      Max number of places to return
        categories: List of category keys from CATEGORY_MAP (default: ["tourism"])
        radius_m:   Search radius in metres (default 8 km)

    Returns:
        List of {name, lat, lon, address, category, wiki_url, website, distance}
    """
    api_key = _api_key()
    if not api_key:
        logger.warning("No API key — returning empty places list.")
        return []

    if not city or not city.strip():
        return []

    lat, lon = _geocode_city(city.strip(), api_key)
    if lat is None:
        logger.warning("Could not geocode city: %s", city)
        return []

    cats = categories or ["tourism"]
    all_places: list[dict] = []
    seen_names: set[str]   = set()

    per_cat_limit = max(limit // len(cats), 5)

    for cat_key in cats:
        api_cat  = CATEGORY_MAP.get(cat_key, cat_key)
        features = _fetch_pois(lat, lon, api_cat, radius_m, per_cat_limit, api_key)

        for f in features:
            parsed = _parse_feature(f)
            if parsed and parsed["name"] not in seen_names:
                seen_names.add(parsed["name"])
                all_places.append(parsed)

        if len(all_places) >= limit:
            break

    # Sort by distance ascending
    all_places.sort(key=lambda x: x.get("distance", 0))

    return all_places[:limit]


def get_city_coordinates(city: str) -> tuple[float, float] | tuple[None, None]:
    """Public helper: geocode a city and return (lat, lon)."""
    api_key = _api_key()
    if not api_key:
        return None, None
    return _geocode_city(city.strip(), api_key)
