"""Philippine place lookup: PSGC (Region > Province > City > Barangay) + Open-Meteo geocoding."""
import math
import re

import requests

from config import GEOCODE_URL, PSGC_BASES, REQUEST_TIMEOUT


# --- PSGC hierarchy ----------------------------------------------------------
def _psgc(path: str):
    last = None
    for base in PSGC_BASES:
        try:
            r = requests.get(f"{base}{path}", timeout=REQUEST_TIMEOUT)
            r.raise_for_status()
            data = r.json()
            if isinstance(data, dict) and "data" in data:
                data = data["data"]
            return data
        except Exception as e:  # try next mirror
            last = e
    raise last


def _norm(items):
    out = [{"code": str(i["code"]), "name": i["name"], "raw": i} for i in items if i.get("code")]
    return sorted(out, key=lambda x: x["name"])


def get_regions():
    return _norm(_psgc("/regions/"))


def get_provinces(region_code):
    return _norm(_psgc(f"/regions/{region_code}/provinces/"))


def get_region_cities(region_code):
    """Cities/municipalities directly under a region (not inside any province)."""
    items = _psgc(f"/regions/{region_code}/cities-municipalities/")
    return _norm([i for i in items if not i.get("provinceCode")])


def get_province_cities(province_code):
    return _norm(_psgc(f"/provinces/{province_code}/cities-municipalities/"))


def get_barangays(city_code):
    return _norm(_psgc(f"/cities-municipalities/{city_code}/barangays/"))


# --- Geocoding ---------------------------------------------------------------
def geocode(name: str, count: int = 10):
    r = requests.get(
        GEOCODE_URL,
        params={"name": name, "count": count, "language": "en", "format": "json", "country_code": "PH"},
        timeout=REQUEST_TIMEOUT,
    )
    r.raise_for_status()
    return [
        {
            "name": x.get("name", ""),
            "lat": x["latitude"],
            "lon": x["longitude"],
            "admin1": x.get("admin1", ""),
            "admin2": x.get("admin2", ""),
        }
        for x in (r.json().get("results") or [])
    ]


def _haversine_km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(a))


def _clean(name: str) -> str:
    name = re.sub(r"\(.*?\)", "", name)
    name = re.sub(r"^City of\s+", "", name, flags=re.I)
    name = re.sub(r"\s+City$", "", name, flags=re.I)
    name = re.sub(r"^Province of\s+", "", name, flags=re.I)
    return name.strip()


def _best(results, province):
    if not results:
        return None
    key = _clean(province).lower()
    if key:
        for r in results:
            if key in f"{r['admin1']} {r['admin2']}".lower():
                return r
    return results[0]


def locate(barangay, city, province):
    """Find coordinates. Returns {'lat','lon','precision'} or None."""
    city_hit = _best(geocode(_clean(city)), province or "")
    if barangay:
        cands = geocode(_clean(barangay))
        if city_hit:
            cands = [c for c in cands
                     if _haversine_km(city_hit["lat"], city_hit["lon"], c["lat"], c["lon"]) <= 40]
            cands.sort(key=lambda c: _haversine_km(city_hit["lat"], city_hit["lon"], c["lat"], c["lon"]))
        else:
            c = _best(cands, province or "")
            cands = [c] if c else []
        if cands:
            return {"lat": cands[0]["lat"], "lon": cands[0]["lon"], "precision": "barangay"}
    if city_hit:
        return {"lat": city_hit["lat"], "lon": city_hit["lon"], "precision": "city"}
    if province:
        p = _best(geocode(_clean(province)), "")
        if p:
            return {"lat": p["lat"], "lon": p["lon"], "precision": "province"}
    return None
