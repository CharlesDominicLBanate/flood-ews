"""
data_fetcher.py
----------------
Handles ingestion of REAL-TIME weather data and SPATIAL (elevation) data.
Uses the free Open-Meteo API (no key required). This is the "streaming
weather data" ingestion layer referenced in the research design.
"""

import random
import time
import requests
import streamlit as st
from config import WEATHER_API_URL, ELEVATION_API_URL, GEOCODING_API_URL

PSGC_BASE = "https://psgc.cloud/api"


@st.cache_data(ttl=86400)  # PSGC data barely changes; cache for a full day
def fetch_psgc_regions():
    """All 17 regions of the Philippines."""
    try:
        resp = requests.get(f"{PSGC_BASE}/regions", timeout=20)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return []


@st.cache_data(ttl=86400)
def fetch_psgc_provinces():
    """All provinces (NCR/BARMM special cities are handled separately as 'independent')."""
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
    """Filter provinces belonging to a region (matched by 2-digit prefix)."""
    provinces = fetch_psgc_provinces()
    prefix = region_code[:2]
    return sorted(
        [p for p in provinces if p.get("code", "")[:2] == prefix],
        key=lambda p: p["name"],
    )


def get_places_for_province(province_code: str):
    """All cities + municipalities under a given province (matched by 4-digit prefix)."""
    prefix = province_code[:4]
    cities = fetch_psgc_cities()
    munis = fetch_psgc_municipalities()
    places = [c for c in cities if c.get("code", "")[:4] == prefix] + \
             [m for m in munis if m.get("code", "")[:4] == prefix]
    return sorted(places, key=lambda p: p["name"])


@st.cache_data(ttl=86400)
def fetch_barangays_for_place(place_code: str):
    """
    All barangays under a given city/municipality PSGC code.

    Tries the direct nested endpoint first; falls back to alternate
    path shapes since PSGC-mirroring APIs aren't always consistent
    about which resource name ('cities-municipalities' vs 'cities' /
    'municipalities') a given code lives under.
    """
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
    """
    Highly urbanized / independent cities that don't sit under any province
    (e.g. Metro Manila cities, Cebu City, Davao City, Baguio, Zamboanga City),
    filtered to the given region.
    """
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
    """'City of Legazpi ' -> 'Legazpi City' style cleanup for geocoding + display."""
    name = raw_name.strip()
    if name.lower().startswith("city of "):
        name = name[8:].strip() + " City"
    return name


@st.cache_data(ttl=3600)
def geocode_location(place_name: str, country_code: str = "PH"):
    """
    Looks up any place name (city, municipality, barangay) and returns its
    coordinates. Lets users monitor ANY location in the Philippines (or
    worldwide) instead of only the predefined list.

    Tries a country-filtered search first; if nothing matches (common when
    the API tags a place with a different/missing country code, or the
    exact PSGC spelling doesn't match Open-Meteo's naming), falls back to
    an unfiltered search so legitimate places still resolve.

    Returns a list of matches: [{"name", "lat", "lon", "admin1", "country"}]
    """
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
    """
    Simulated weather generator used for offline demos / thesis defense
    when no internet connection is available. Produces plausible, randomly
    varying values so the dashboard still feels 'live'.
    """
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

        # Grab the most recent hourly soil moisture reading available
        soil_moisture_series = hourly.get("soil_moisture_0_to_1cm", [])
        soil_moisture = soil_moisture_series[0] if soil_moisture_series else 0.2

        # Sum next-24h forecast precipitation as an "accumulation" signal
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
        # Fail gracefully so the dashboard keeps running even if the API hiccups
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
    """Spatial data: ground elevation (meters) at a coordinate."""
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


def _get_with_retry(url: str, params: dict, timeout: int, retries: int = 2):
    """
    GET with a couple of retries + short backoff, specifically to absorb
    transient 429 (rate limit) responses gracefully instead of failing
    the whole batch outright.
    """
    delay = 1.0
    last_exc = None
    for attempt in range(retries + 1):
        try:
            resp = requests.get(url, params=params, timeout=timeout)
            if resp.status_code == 429 and attempt < retries:
                time.sleep(delay)
                delay *= 2
                continue
            resp.raise_for_status()
            return resp
        except Exception as e:
            last_exc = e
            if attempt < retries:
                time.sleep(delay)
                delay *= 2
    if last_exc:
        raise last_exc


@st.cache_data(ttl=300)
def fetch_current_weather_batch(coords: tuple) -> dict:
    """
    Fetches weather for MANY locations in a SINGLE Open-Meteo request,
    using its comma-separated multi-location support. This replaces N
    separate calls (one per monitored site) with just one — the previous
    per-location loop was firing ~20 near-simultaneous requests every
    time the shared 5-minute cache expired (since all sites were first
    populated together), which is exactly the kind of burst that trips
    Open-Meteo's rate limiting (HTTP 429).

    coords: tuple of (lat, lon) tuples, in the exact order results are needed.
    Returns: dict mapping the (lat, lon) tuple -> weather dict (same shape
             as fetch_current_weather's return value).
    """
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
        # Fail gracefully for ALL locations at once so the dashboard still
        # renders with fallback values instead of crashing.
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
    """
    Same batching idea as fetch_current_weather_batch, but for elevation.
    Returns: dict mapping (lat, lon) -> elevation in meters.
    """
    if not coords:
        return {}

    lats = ",".join(str(c[0]) for c in coords)
    lons = ",".join(str(c[1]) for c in coords)

    try:
        resp = _get_with_retry(
            ELEVATION_API_URL, {"latitude": lats, "longitude": lons}, timeout=15
        )
        data = resp.json()
        elevations = data.get("elevation", [])
        return {coord: elevations[i] if i < len(elevations) else 0.0
                 for i, coord in enumerate(coords)}
    except Exception:
        return {coord: 0.0 for coord in coords}
