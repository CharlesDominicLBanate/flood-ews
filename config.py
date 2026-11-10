"""Central configuration for the Flash Flood Early Warning System."""

# --- Chaos simulation (Lorenz system) ---
SIM_STEPS = 2000
SIM_DT = 0.01
LYAPUNOV_EPSILON = 1e-6
DEFAULT_SLOPE_FACTOR = 0.6   # terrain vulnerability used when no slope data is available

# --- Risk classification: (low, high, label, color) ---
RISK_LEVELS = [
    (0, 25, "LOW", "#2ecc71"),
    (25, 50, "MODERATE", "#f1c40f"),
    (50, 75, "HIGH", "#e67e22"),
    (75, 100.0001, "CRITICAL", "#e74c3c"),
]

# --- APIs (all free, no key needed) ---
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
ELEVATION_URL = "https://api.open-meteo.com/v1/elevation"
GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
PSGC_BASES = ["https://psgc.gitlab.io/api", "https://psgc.cloud/api"]
TIMEZONE = "Asia/Manila"
FORECAST_HOURS = 24
REQUEST_TIMEOUT = 15

# --- Map ---
MAP_CENTER = (12.5, 122.0)
MAP_ZOOM = 6
MAP_REFRESH_SECONDS = 600     # how often the regional map re-fetches all sites

# --- Default monitoring sites ---
DEFAULT_SITE = "Metro Manila (Marikina City)"
PRESET_SITES = {
    "Metro Manila (Marikina City)": (14.6507, 121.1029),
    "Angeles City": (15.1450, 120.5887),
    "Baguio City": (16.4023, 120.5960),
    "Tuguegarao City": (17.6132, 121.7270),
    "Batangas City": (13.7565, 121.0583),
    "Naga City": (13.6218, 123.1948),
    "Legazpi City": (13.1391, 123.7438),
    "Puerto Princesa City": (9.7392, 118.7353),
    "Roxas City": (11.5853, 122.7511),
    "Iloilo City": (10.7202, 122.5621),
    "Cebu City": (10.3157, 123.8854),
    "Tacloban City": (11.2543, 124.9630),
    "Cagayan de Oro City": (8.4542, 124.6319),
    "Davao City": (7.1907, 125.4553),
    "Zamboanga City": (6.9214, 122.0790),
}
