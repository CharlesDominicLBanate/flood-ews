"""Weather data: live from Open-Meteo, or simulated for offline demo mode."""
import random
from datetime import datetime

import requests

from config import FORECAST_HOURS, REQUEST_TIMEOUT, TIMEZONE, WEATHER_URL


def fetch_weather(lat: float, lon: float) -> dict:
    """Live weather + elevation + 24h forecast from Open-Meteo."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,precipitation,rain",
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

    now_hour = current.get("time", datetime.now().strftime("%Y-%m-%dT%H:00"))[:13] + ":00"
    try:
        idx = times.index(now_hour)
    except ValueError:
        idx = min(24, len(times) - 1)

    soil_now = soil[idx] if idx < len(soil) and soil[idx] is not None else 0.2

    return {
        "rain_mm": float(current.get("rain") or 0.0),
        "precipitation_mm": float(current.get("precipitation") or 0.0),
        "precip_accum_24h_mm": float(sum(precip[max(0, idx - 23): idx + 1])),
        "humidity_pct": float(current.get("relative_humidity_2m") or 50.0),
        "temp_c": float(current.get("temperature_2m") or 0.0),
        "soil_moisture": float(soil_now),
        "hourly_precip": [float(p) for p in precip[idx + 1: idx + 1 + FORECAST_HOURS]],
        "elevation": float(data.get("elevation") or 0.0),
        "fetched_at": current.get("time", ""),
        "simulated": False,
    }


# --- Offline demo mode -------------------------------------------------------
# scenario: (rain mm/hr, 24h accum mm, humidity %, soil moisture)
SCENARIOS = {
    "Calm weather": ((0.0, 1.0), (0.0, 8.0), (65, 85), (0.15, 0.30)),
    "Heavy rain": ((8.0, 16.0), (60.0, 110.0), (88, 96), (0.38, 0.50)),
    "Typhoon / extreme rain": ((22.0, 40.0), (130.0, 230.0), (94, 100), (0.50, 0.62)),
}


def simulate_weather(lat: float, lon: float, scenario: str = "Heavy rain") -> dict:
    """Deterministic fake weather so the dashboard works without internet."""
    rain_r, acc_r, hum_r, soil_r = SCENARIOS[scenario]
    rng = random.Random(f"{lat:.3f}|{lon:.3f}|{scenario}")
    rain = rng.uniform(*rain_r)
    hourly = []
    level = rain
    for _ in range(FORECAST_HOURS):
        level = max(0.0, level * rng.uniform(0.75, 1.05) + rng.uniform(-1.0, 1.0) * (rain > 1))
        hourly.append(round(level, 2))
    return {
        "rain_mm": round(rain, 2),
        "precipitation_mm": round(rain, 2),
        "precip_accum_24h_mm": round(rng.uniform(*acc_r), 1),
        "humidity_pct": round(rng.uniform(*hum_r)),
        "temp_c": round(rng.uniform(24, 31), 1),
        "soil_moisture": round(rng.uniform(*soil_r), 2),
        "hourly_precip": hourly,
        "elevation": float(round(rng.uniform(5, 300))),
        "fetched_at": datetime.now().strftime("%Y-%m-%dT%H:%M"),
        "simulated": True,
    }
