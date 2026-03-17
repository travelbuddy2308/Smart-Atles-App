# Smart Atlas ✈️

An AI-powered travel companion built with Streamlit.  
Real places (Geoapify), real weather (OpenWeatherMap), interactive maps (Folium + OSM).

---

## Project Structure

```
smart_atlas/
├── app.py                        ← Entry point (run this)
├── requirements.txt
├── .gitignore
├── .streamlit/
│   └── secrets.toml              ← API keys & DB creds (NOT in Git)
├── pages/
│   ├── login.py                  ← Login · Sign-Up · Forgot Password
│   ├── home.py                   ← Dashboard
│   ├── itinerary.py              ← Day-by-day trip planner
│   ├── map_page.py               ← Travel Explorer (map + places)
│   ├── planner.py                ← Trip Cost Planner (fh.py rewritten)
│   └── feedback.py               ← Multi-step feedback form
├── utils/
│   ├── auth.py                   ← Password hashing, session helpers
│   ├── costs.py                  ← Unified cost model (single source of truth)
│   ├── db.py                     ← MySQL + SQLite context managers
│   ├── theme.py                  ← CSS design system
│   └── tts.py                   ← Text-to-speech (single definition)
└── services/
    ├── weather_service.py        ← OpenWeatherMap
    ├── places_service.py         ← Geoapify geocode + POI search
    ├── overpass_service.py       ← OSM Overpass (hotels & restaurants near coords)
    └── map_service.py            ← Folium map builder
```

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure secrets

Copy the template and fill in your keys:

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```

```toml
[api]
geoapify_key    = "YOUR_GEOAPIFY_KEY"
openweather_key = "YOUR_OPENWEATHER_KEY"

[mysql]
host     = "localhost"
port     = 3306
user     = "root"
password = "your_password"
database = "smart_atlas"
```

Get free API keys from:
- Geoapify: https://myprojects.geoapify.com
- OpenWeatherMap: https://openweathermap.org/api

### 3. Create the MySQL database

```sql
CREATE DATABASE smart_atlas;
```
The `users` table is created automatically on first run.

### 4. Run

```bash
streamlit run app.py
```

---

## Changes from Original Codebase

| Issue | Fix |
|---|---|
| API keys hardcoded in source | Moved to `.streamlit/secrets.toml` |
| `st.set_page_config()` in multiple files causing conflicts | One call per page file only |
| Nominatim misused for proximity search (doesn't support radius) | Replaced with Overpass API |
| Two conflicting cost models (`COST_PROFILES` vs `BASE_COSTS`) | Unified in `utils/costs.py` |
| Duplicate `speak()` function in multiple files | Single definition in `utils/tts.py` |
| Global `sqlite3.connect()` / `mysql.connector.connect()` | Context-manager helpers in `utils/db.py` |
| `feedback.py` post-submit display using wrong session keys | Fixed — values stored correctly before rerun |
| Bare `except:` clauses swallowing all errors | Replaced with specific exception handling |
| No navigation flow between pages | `st.switch_page()` wired throughout |
| `map_service.py` generated map but never saved it | `save_map()` function added |
| Hardcoded Windows asset paths in `log_p.py` | Removed — logo uses emoji fallback |
