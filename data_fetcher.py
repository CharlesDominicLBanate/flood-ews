"""
data_fetcher.py — Open-Meteo weather fetcher with caching + retry/backoff.

Fixes the "429 Too Many Requests -> fallback values" issue by:
  1. Caching results (st.cache_data) so Streamlit reruns don't re-hit the API.
  2. Retrying failed requests with exponential backoff + jitter, honoring
     the Retry-After header when Open-Meteo sends one.
  3. Still batching all locations into a single request (comma-separated
     lat/lon lists), which is the efficient pattern you already had.

NOTE: I could not recover your original data_fetcher.py (the uploaded file
was corrupted / contained a GitHub rate-limit error instead of code), so
this is a clean rebuild based on the weather-dict shape your chaos_model.py
expects (rain_mm, precipitation_mm, precip_accum_24h_mm, humidity_pct,
soil_moisture). If your real function names/signatures differ, send me the
real file (or app.py) and I'll merge this logic into it exactly.
"""

import time
import random
import requests
import streamlit as st

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

MAX_RETRIES = 4
BASE_BACKOFF_SECONDS = 2.0   # 2s, 4s, 8s, 16s (+jitter)
REQUEST_TIMEOUT = 10
CACHE_TTL_SECONDS = 600      # 10 min — tune to taste


def _request_with_retry(params: dict) -> requests.Response | None:
    """GET with exponential backoff + jitter. Returns None if all retries fail."""
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(OPEN_METEO_URL, params=params, timeout=REQUEST_TIMEOUT)
        except requests.RequestException:
            resp = None

        if resp is not None and resp.status_code == 200:
            return resp

        if resp is not None and resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After")
            if retry_after is not None:
                try:
                    wait = float(retry_after)
                except ValueError:
                    wait = BASE_BACKOFF_SECONDS * (2 ** attempt)
            else:
                wait = BASE_BACKOFF_SECONDS * (2 ** attempt)
            wait += random.uniform(0, 1.0)  # jitter avoids thundering herd
        else:
            # 5xx or network error — back off too, but shorter
            wait = BASE_BACKOFF_SECONDS * (2 ** attempt) * 0.5 + random.uniform(0, 0.5)

        if attempt < MAX_RETRIES - 1:
            time.sleep(wait)

    return None  # exhausted retries — caller should show the fallback banner


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def fetch_weather_batch(locations: dict[str, tuple[float, float]]) -> dict:
    """
    locations: {"Marikina City": (14.6507, 121.1029), ...}

    Returns: {"Marikina City": {
                  "rain_mm": ..., "precipitation_mm": ...,
                  "precip_accum_24h_mm": ..., "humidity_pct": ...,
                  "soil_moisture": ..., "is_fallback": False
              }, ...}
    """
    names = list(locations.keys())
    lats = ",".join(str(locations[n][0]) for n in names)
    lons = ",".join(str(locations[n][1]) for n in names)

    params = {
        "latitude": lats,
        "longitude": lons,
        "current": "precipitation,rain,relative_humidity_2m,temperature_2m,"
                   "wind_speed_10m,surface_pressure",
        "hourly": "precipitation,soil_moisture_0_to_1cm",
        "forecast_days": 1,
        "timezone": "auto",
    }

    resp = _request_with_retry(params)

    if resp is None:
        return {name: _fallback_weather() for name in names}

    try:
        data = resp.json()
    except ValueError:
        return {name: _fallback_weather() for name in names}

    # Open-Meteo returns a list of per-location objects when lat/lon are
    # comma-separated lists; a single dict when there's only one location.
    entries = data if isinstance(data, list) else [data]

    results = {}
    for name, entry in zip(names, entries):
        try:
            current = entry.get("current", {})
            hourly = entry.get("hourly", {})
            hourly_precip = hourly.get("precipitation", []) or []
            soil_series = hourly.get("soil_moisture_0_to_1cm", []) or []

            results[name] = {
                "rain_mm": current.get("rain", 0.0) or 0.0,
                "precipitation_mm": current.get("precipitation", 0.0) or 0.0,
                "precip_accum_24h_mm": sum(v for v in hourly_precip if v is not None),
                "humidity_pct": current.get("relative_humidity_2m", 50.0) or 50.0,
                "soil_moisture": (soil_series[0] if soil_series else 0.2) or 0.2,
                "is_fallback": False,
            }
        except (AttributeError, IndexError, TypeError):
            results[name] = _fallback_weather()

    return results


def _fallback_weather() -> dict:
    return {
        "rain_mm": 0.0,
        "precipitation_mm": 0.0,
        "precip_accum_24h_mm": 0.0,
        "humidity_pct": 50.0,
        "soil_moisture": 0.2,
        "is_fallback": True,
    }
