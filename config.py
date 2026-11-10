"""Central configuration for the Flash Flood Risk Index (FFRI) app."""

# --- Chaos simulation (Lorenz system) ---
SIM_STEPS = 2000
SIM_DT = 0.01
LYAPUNOV_EPSILON = 1e-6

# --- Risk classification: (low, high, label, color) ---
RISK_LEVELS = [
    (0, 25, "LOW", "#2ecc71"),
    (25, 50, "MODERATE", "#f1c40f"),
    (50, 75, "HIGH", "#e67e22"),
    (75, 100.0001, "CRITICAL", "#e74c3c"),
]

# --- Open-Meteo ---
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
TIMEZONE = "Asia/Manila"
FORECAST_HOURS = 12
REQUEST_TIMEOUT = 15
CACHE_TTL_SECONDS = 600

# --- Map defaults (Philippines) ---
MAP_CENTER = (12.5, 122.0)
MAP_ZOOM = 6

# --- Locations: lat, lon, slope_factor (0 = flat, 1 = very steep) ---
LOCATIONS = {
    "Metro Manila": {"lat": 14.5995, "lon": 120.9842, "slope": 0.15},
    "Baguio": {"lat": 16.4023, "lon": 120.5960, "slope": 0.85},
    "Tuguegarao": {"lat": 17.6132, "lon": 121.7270, "slope": 0.20},
    "Legazpi": {"lat": 13.1391, "lon": 123.7438, "slope": 0.65},
    "Tacloban": {"lat": 11.2543, "lon": 124.9630, "slope": 0.35},
    "Iloilo City": {"lat": 10.7202, "lon": 122.5621, "slope": 0.15},
    "Cebu City": {"lat": 10.3157, "lon": 123.8854, "slope": 0.60},
    "Cagayan de Oro": {"lat": 8.4542, "lon": 124.6319, "slope": 0.50},
    "Davao City": {"lat": 7.1907, "lon": 125.4553, "slope": 0.40},
    "Zamboanga City": {"lat": 6.9214, "lon": 122.0790, "slope": 0.40},
}
