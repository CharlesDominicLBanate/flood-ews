import random
import time
import requests
import streamlit as st
from config import WEATHER_API_URL, ELEVATION_API_URL, GEOCODING_API_URL

PSGC_BASE = "https://psgc.cloud/api"


@st.cache_data(ttl=86400)  # PSGC data barely changes; cache for a full day
def fetch_psgc_regions():
    try:
        resp = requests.get(f"{PSGC_BASE}/regions", timeout=20)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return []


@st.cache_data(ttl=86400)
def fetch_psgc_provinces():
    try:
        resp = requests.get(f"{PSGC_BASE}/provinces", timeout=20)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return []


@st.cache_data(ttl=86400)
def fetch_psgc_cities():
    try:
        resp = requests.get(f"{PSGC_BASE}/cities", timeout=20)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return []


@st.cache_data(ttl=86400)
def fetch_psgc_municipalities():
    try:
        resp = requests.get(f"{PSGC_BASE}/municipalities", timeout=25)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return []


def get_provinces_for_region(region_code: str):
    provinces = fetch_psgc_provinces()
    prefix = region_code[:2]
    return sorted(
        [p for p in provinces if p.get("code", "")[:2] == prefix],
        key=lambda p: p["name"],
    )


def get_places_for_province(province_code: str):
    prefix = province_code[:4]
    cities = fetch_psgc_cities()
    munis = fetch_psgc_municipalities()
    places = [c for c in cities if c.get("code", "")[:4] == prefix] + \
             [m for m in munis if m.get("code", "")[:4] == prefix]
    return sorted(places, key=lambda p: p["name"])


@st.cache_data(ttl=86400)
def fetch_barangays_for_place(place_code: str):
    candidate_urls = [
        f"{PSGC_BASE}/cities-municipalities/{place_code}/barangays",
        f"{PSGC_BASE}/cities/{place_code}/barangays",
        f"{PSGC_BASE}/municipalities/{place_code}/barangays",
    ]
    for url in candidate_urls:
        try:
            resp = requests.get(url, timeout=20)
            if resp.ok:
                data = resp.json()
                items = data.get("data", data) if isinstance(data, dict) else data
                if items:
                    return sorted(items, key=lambda b: b["name"])
        except Exception:
            continue
    return []


def get_independent_cities_for_region(region_code: str):
    prefix = region_code[:2]
    all_provinces = fetch_psgc_provinces()
    province_prefixes = {p.get("code", "")[:4] for p in all_provinces}
    cities = fetch_psgc_cities()
    independent = [
        c for c in cities
        if c.get("code", "")[:2] == prefix and c.get("code", "")[:4] not in province_prefixes
    ]
    return sorted(independent, key=lambda p: p["name"])


def clean_place_name(raw_name: str) -> str:
    name = raw_name.strip()
    if name.lower().startswith("city of "):
        name = name[8:].strip() + " City"
    return name


@st.cache_data(ttl=3600)
def geocode_location(place_name: str, country_code: str = "PH"):
    def _query(name):
        try:
            resp = requests.get(
                GEOCODING_API_URL,
                params={"name": name, "count": 8, "language": "en", "format": "json"},
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json().get("results", [])
        except Exception:
            return []

    def _to_matches(results, filter_country):
        matches = []
        for r in results:
            if filter_country and country_code and r.get("country_code") != country_code:
                continue
            label = r.get("name", place_name)
            admin1 = r.get("admin1", "")
            if admin1:
                label = f"{label}, {admin1}"
            matches.append({"name": label, "lat": r["latitude"], "lon": r["longitude"]})
        return matches

    raw = _query(place_name)
    matches = _to_matches(raw, filter_country=True)
    if matches:
        return matches

    # Fallback 1: same query, no country filter (in case tagging differs)
    matches = _to_matches(raw, filter_country=False)
    if matches:
        return matches

    # Fallback 2: strip common suffixes like "City"/"Municipality" and retry
    stripped = place_name.replace(" City", "").replace(" Municipality", "").strip()
    if stripped and stripped != place_name:
        raw2 = _query(stripped)
        matches = _to_matches(raw2, filter_country=True) or _to_matches(raw2, filter_country=False)

    return matches


def generate_demo_weather(lat: float, lon: float) -> dict:

    rng = random.Random(f"{lat:.2f}{lon:.2f}{int(__import__('time').time() // 30)}")
    rain = max(0.0, rng.gauss(6, 8))
    humidity = min(100, max(40, rng.gauss(80, 10)))
    accum = max(0.0, rng.gauss(45, 35))
    soil_moisture = min(0.6, max(0.05, rng.gauss(0.25, 0.12)))
    hourly_precip = [max(0.0, rng.gauss(rain * 0.6, 3)) for _ in range(24)]

    return {
        "success": True,
        "demo_mode": True,
        "precipitation_mm": rain,
        "rain_mm": rain,
        "humidity_pct": humidity,
        "temperature_c": rng.gauss(27, 2),
        "wind_speed_kmh": max(0.0, rng.gauss(12, 6)),
        "pressure_hpa": rng.gauss(1008, 4),
        "soil_moisture": soil_moisture,
        "precip_accum_24h_mm": accum,
        "hourly_precip_series": hourly_precip,
    }


@st.cache_data(ttl=300)  # cache 5 min so we don't hammer the API on every rerun
def fetch_current_weather(lat: float, lon: float) -> dict:
    """
    Pulls current + short-horizon hourly weather for a coordinate.
    Returns a flat dict of the variables the chaos model needs.
    """
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": ",".join([
            "precipitation",
            "rain",
            "relative_humidity_2m",
            "temperature_2m",
            "wind_speed_10m",
            "surface_pressure",
        ]),
        "hourly": ",".join([
            "precipitation",
            "soil_moisture_0_to_1cm",
        ]),
        "forecast_days": 1,
        "timezone": "auto",
    }

    try:
        resp = requests.get(WEATHER_API_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        current = data.get("current", {})
        hourly = data.get("hourly", {})


        soil_moisture_series = hourly.get("soil_moisture_0_to_1cm", [])
        soil_moisture = soil_moisture_series[0] if soil_moisture_series else 0.2


        precip_series = hourly.get("precipitation", [])
        precip_accum_24h = sum(v for v in precip_series if v is not None)

        return {
            "success": True,
            "precipitation_mm": current.get("precipitation", 0.0) or 0.0,
            "rain_mm": current.get("rain", 0.0) or 0.0,
            "humidity_pct": current.get("relative_humidity_2m", 50.0) or 50.0,
            "temperature_c": current.get("temperature_2m", 25.0) or 25.0,
            "wind_speed_kmh": current.get("wind_speed_10m", 0.0) or 0.0,
            "pressure_hpa": current.get("surface_pressure", 1013.0) or 1013.0,
            "soil_moisture": soil_moisture if soil_moisture is not None else 0.2,
            "precip_accum_24h_mm": precip_accum_24h,
            "hourly_precip_series": precip_series[:24],
        }

    except Exception as e:

        return {
            "success": False,
            "error": str(e),
            "precipitation_mm": 0.0,
            "rain_mm": 0.0,
            "humidity_pct": 50.0,
            "temperature_c": 25.0,
            "wind_speed_kmh": 0.0,
            "pressure_hpa": 1013.0,
            "soil_moisture": 0.2,
            "precip_accum_24h_mm": 0.0,
            "hourly_precip_series": [],
        }


@st.cache_data(ttl=3600)
def fetch_elevation(lat: float, lon: float) -> float:

    try:
        resp = requests.get(
            ELEVATION_API_URL,
            params={"latitude": lat, "longitude": lon},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("elevation", [0.0])[0]
    except Exception:
        return 0.0


# Module-level (app-wide, shared across ALL user sessions since Streamlit
# runs one process) timestamp of the last time we actually hit Open-Meteo.
# This is a simple global throttle so that bursts of reruns/sessions can't
# collectively hammer the API faster than a safe minimum spacing, even if
# their cache keys differ (e.g. different custom-location sets per user).
_last_weather_call_ts = 0.0
_last_elevation_call_ts = 0.0
_MIN_CALL_SPACING_SECONDS = 2.0  # be polite to the free/shared API


def _throttle(last_ts_attr: str, min_spacing: float = _MIN_CALL_SPACING_SECONDS):
    global _last_weather_call_ts, _last_elevation_call_ts
    now = time.monotonic()
    last_ts = globals()[last_ts_attr]
    wait = min_spacing - (now - last_ts)
    if wait > 0:
        time.sleep(wait)
    globals()[last_ts_attr] = time.monotonic()


def _get_with_retry(url: str, params: dict, timeout: int, retries: int = 4):
    """
    GET with exponential backoff. Crucially, if the server sends a
    Retry-After header on a 429, we honor THAT value instead of guessing —
    Open-Meteo (and most APIs) tell you exactly how long to back off.
    """
    delay = 2.0
    last_exc = None
    for attempt in range(retries + 1):
        try:
            resp = requests.get(url, params=params, timeout=timeout)
            if resp.status_code == 429 and attempt < retries:
                retry_after = resp.headers.get("Retry-After")
                if retry_after is not None:
                    try:
                        sleep_for = float(retry_after)
                    except ValueError:
                        sleep_for = delay
                else:
                    sleep_for = delay
                # add small jitter so many concurrent sessions don't all
                # wake up and retry at the exact same instant
                sleep_for += random.uniform(0, 0.5)
                time.sleep(sleep_for)
                delay *= 2
                continue
            resp.raise_for_status()
            return resp
        except requests.exceptions.HTTPError as e:
            last_exc = e
            if attempt < retries:
                time.sleep(delay + random.uniform(0, 0.5))
                delay *= 2
        except Exception as e:
            last_exc = e
            if attempt < retries:
                time.sleep(delay + random.uniform(0, 0.5))
                delay *= 2
    if last_exc:
        raise last_exc


@st.cache_data(ttl=600)  # was 300s — widened to 10 min to cut call volume
def fetch_current_weather_batch(coords: tuple) -> dict:

    if not coords:
        return {}

    lats = ",".join(str(c[0]) for c in coords)
    lons = ",".join(str(c[1]) for c in coords)

    params = {
        "latitude": lats,
        "longitude": lons,
        "current": ",".join([
            "precipitation", "rain", "relative_humidity_2m",
            "temperature_2m", "wind_speed_10m", "surface_pressure",
        ]),
        "hourly": ",".join(["precipitation", "soil_moisture_0_to_1cm"]),
        "forecast_days": 1,
        "timezone": "auto",
    }

    try:
        _throttle("_last_weather_call_ts")
        resp = _get_with_retry(WEATHER_API_URL, params, timeout=20)
        data = resp.json()
        # Open-Meteo returns a LIST of per-location objects when multiple
        # lat/lon values are passed, in the same order they were given.
        entries = data if isinstance(data, list) else [data]

        out = {}
        for coord, entry in zip(coords, entries):
            current = entry.get("current", {})
            hourly = entry.get("hourly", {})
            soil_series = hourly.get("soil_moisture_0_to_1cm", [])
            soil_moisture = soil_series[0] if soil_series else 0.2
            precip_series = hourly.get("precipitation", [])
            precip_accum_24h = sum(v for v in precip_series if v is not None)

            out[coord] = {
                "success": True,
                "precipitation_mm": current.get("precipitation", 0.0) or 0.0,
                "rain_mm": current.get("rain", 0.0) or 0.0,
                "humidity_pct": current.get("relative_humidity_2m", 50.0) or 50.0,
                "temperature_c": current.get("temperature_2m", 25.0) or 25.0,
                "wind_speed_kmh": current.get("wind_speed_10m", 0.0) or 0.0,
                "pressure_hpa": current.get("surface_pressure", 1013.0) or 1013.0,
                "soil_moisture": soil_moisture if soil_moisture is not None else 0.2,
                "precip_accum_24h_mm": precip_accum_24h,
                "hourly_precip_series": precip_series[:24],
            }
        return out

    except Exception as e:

        fallback = {
            "success": False,
            "error": str(e),
            "precipitation_mm": 0.0,
            "rain_mm": 0.0,
            "humidity_pct": 50.0,
            "temperature_c": 25.0,
            "wind_speed_kmh": 0.0,
            "pressure_hpa": 1013.0,
            "soil_moisture": 0.2,
            "precip_accum_24h_mm": 0.0,
            "hourly_precip_series": [],
        }
        return {coord: dict(fallback) for coord in coords}


@st.cache_data(ttl=3600)
def fetch_elevation_batch(coords: tuple) -> dict:

    if not coords:
        return {}

    lats = ",".join(str(c[0]) for c in coords)
    lons = ",".join(str(c[1]) for c in coords)

    try:
        _throttle("_last_elevation_call_ts")
        resp = _get_with_retry(
            ELEVATION_API_URL, {"latitude": lats, "longitude": lons}, timeout=15
        )
        data = resp.json()
        elevations = data.get("elevation", [])
        return {coord: elevations[i] if i < len(elevations) else 0.0
                 for i, coord in enumerate(coords)}
    except Exception:
        return {coord: 0.0 for coord in coords}
