"""Real terrain vulnerability from elevation data (Open-Meteo elevation API, ~90 m DEM).

Samples elevations around a point (near ring ~1 km, far ring ~4.4 km) and derives:
  - local slope (steep terrain -> fast runoff)
  - relief: how much lower the point is than its surroundings (low-lying -> water collects)
  - absolute elevation (very low ground -> flood/coastal exposure)
and combines them into a 0-1 terrain vulnerability factor.

The weights are heuristic and should be calibrated against real flood events.
"""
import math
import random

import requests

from config import DEFAULT_SLOPE_FACTOR, ELEVATION_URL, REQUEST_TIMEOUT

NEAR_DEG = 0.01   # ~1.1 km
FAR_DEG = 0.04    # ~4.4 km
KM_PER_DEG = 111.32

_cache = {}


def _grid(lat, lon):
    """Return list of points: center, 8 near, 8 far (lat, lon)."""
    pts = [(lat, lon)]
    for step in (NEAR_DEG, FAR_DEG):
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dx or dy:
                    pts.append((lat + dy * step, lon + dx * step))
    return pts


def _near_distances_m(lat):
    out = []
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dx or dy:
                north = dy * NEAR_DEG * KM_PER_DEG * 1000
                east = dx * NEAR_DEG * KM_PER_DEG * 1000 * math.cos(math.radians(lat))
                out.append(math.hypot(north, east))
    return out


def score_terrain(center, near, far, near_dists_m):
    """Pure function: elevations (m) -> terrain metrics and 0-1 factor."""
    grads = [abs(z - center) / d for z, d in zip(near, near_dists_m)]
    slope_deg = math.degrees(math.atan(sum(grads) / len(grads)))
    relief = sum(far) / len(far) - center          # > 0: lower than surroundings

    slope_score = min(slope_deg / 10.0, 1.0)
    low_score = min(max(relief / 40.0, 0.0), 1.0)
    elev_score = min(max(1.0 - center / 100.0, 0.0), 1.0)

    factor = 0.40 * slope_score + 0.35 * low_score + 0.25 * elev_score
    return {"slope_deg": slope_deg, "relief_m": relief, "elevation_m": center,
            "factor": float(min(max(factor, 0.0), 1.0))}


def _fetch_elevations(points):
    r = requests.get(
        ELEVATION_URL,
        params={"latitude": ",".join(f"{p[0]:.5f}" for p in points),
                "longitude": ",".join(f"{p[1]:.5f}" for p in points)},
        timeout=REQUEST_TIMEOUT,
    )
    r.raise_for_status()
    elev = r.json()["elevation"]
    if len(elev) != len(points) or any(e is None for e in elev):
        raise ValueError("incomplete elevation data")
    return elev


def get_terrain(lat, lon, offline=False):
    """Terrain vulnerability for a point. Never raises; falls back to a default."""
    key = (round(lat, 3), round(lon, 3), bool(offline))
    if key in _cache:
        return _cache[key]

    if offline:
        rng = random.Random(f"terrain|{key}")
        result = {"slope_deg": rng.uniform(0.5, 8), "relief_m": rng.uniform(-10, 30),
                  "elevation_m": rng.uniform(5, 300), "factor": rng.uniform(0.2, 0.8),
                  "source": "simulated"}
        _cache[key] = result
        return result

    try:
        e = _fetch_elevations(_grid(lat, lon))
        result = score_terrain(e[0], e[1:9], e[9:17], _near_distances_m(lat))
        result["source"] = "elevation data (90 m DEM)"
        _cache[key] = result            # only cache successes
        return result
    except Exception:
        return {"slope_deg": 0.0, "relief_m": 0.0, "elevation_m": 0.0,
                "factor": DEFAULT_SLOPE_FACTOR, "source": "default (elevation data unavailable)"}
