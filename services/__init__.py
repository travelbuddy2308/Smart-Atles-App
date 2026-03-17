# services/__init__.py
# Smart Atles — Services Package
# Exposes all service functions for clean imports across the app.

from services.weather_service import get_weather_by_city
from services.places_service  import get_places_for_city
from services.hotel_service   import get_hotels_near
from services.food_service    import get_food_near
from services.map_service     import (
    generate_day_map, save_map,
    sort_by_proximity, get_top_attractions,
    fetch_transport_stops_osm, TILE_STYLES,
)

# Audio / Language service (optional — graceful if dependencies missing)
try:
    from services.audio_service import (
        play_tts, play_tts_hidden, play_welcome_greeting,
        play_day_chime, narrate_itinerary_day,
        detect_language, get_city_language, get_local_phrase,
        get_language_name, render_music_toggle,
    )
    _AUDIO_EXPORTS = [
        "play_tts", "play_tts_hidden", "play_welcome_greeting",
        "play_day_chime", "narrate_itinerary_day",
        "detect_language", "get_city_language", "get_local_phrase",
        "get_language_name", "render_music_toggle",
    ]
except Exception:
    _AUDIO_EXPORTS = []

__all__ = [
    # Weather
    "get_weather_by_city",
    # Places
    "get_places_for_city",
    # Hotels
    "get_hotels_near",
    # Food
    "get_food_near",
    # Maps
    "generate_day_map", "save_map",
    "sort_by_proximity", "get_top_attractions",
    "fetch_transport_stops_osm", "TILE_STYLES",
    # Audio (if available)
    *_AUDIO_EXPORTS,
]
