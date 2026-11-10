"""Fetch weather + elevation from Open-Meteo (free, no API key)."""
from datetime import datetime

import requests

from config import WEATHER_URL, TIMEZONE, FORECAST_HOURS, REQUEST_TIMEOUT


def fetch_weather(lat: float, lon: float) -> dict:
    """Return the weather dict expected by chaos_model, plus elevation and hourly forecast."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "relative_humidity_2m,precipitation,rain",
        "hourly": "precipitation,soil_moisture_0_to_7cm",
        "past_days": 1,
        "forecast_days": 2,
        "timezone": TIMEZONE,
    }
    resp = requests.get(WEATHER_URL, params=params, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()

    current = data.get("current", {})
    hourly = data.get("hourly", {})
    times = hourly.get("time", [])
    precip = [p if p is not None else 0.0 for p in hourly.get("precipitation", [])]
    soil = hourly.get("soil_moisture_0_to_7cm", [])

    # Find the index of the current hour
    now_hour = current.get("time", datetime.now().strftime("%Y-%m-%dT%H:00"))[:13] + ":00"
    try:
        idx = times.index(now_hour)
    except ValueError:
        idx = min(24, len(times) - 1)

    accum_24h = float(sum(precip[max(0, idx - 23): idx + 1]))
    hourly_precip = [float(p) for p in precip[idx + 1: idx + 1 + FORECAST_HOURS]]

    soil_now = soil[idx] if idx < len(soil) and soil[idx] is not None else 0.2

    return {
        "rain_mm": float(current.get("rain") or 0.0),
        "precipitation_mm": float(current.get("precipitation") or 0.0),
        "precip_accum_24h_mm": accum_24h,
        "humidity_pct": float(current.get("relative_humidity_2m") or 50.0),
        "soil_moisture": float(soil_now),
        "hourly_precip": hourly_precip,
        "elevation": float(data.get("elevation") or 0.0),
        "fetched_at": current.get("time", ""),
    }
