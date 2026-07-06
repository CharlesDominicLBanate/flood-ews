
LOCATIONS = {
    # Luzon
    "Metro Manila (Marikina City)": {"lat": 14.6507, "lon": 121.1029, "slope_factor": 0.85},
    "Quezon City":                  {"lat": 14.6760, "lon": 121.0437, "slope_factor": 0.60},
    "Baguio City":                  {"lat": 16.4023, "lon": 120.5960, "slope_factor": 0.80},
    "Tuguegarao City":              {"lat": 17.6132, "lon": 121.7270, "slope_factor": 0.55},
    "Dagupan City":                 {"lat": 16.0433, "lon": 120.3333, "slope_factor": 0.50},
    "Naga City":                    {"lat": 13.6218, "lon": 123.1948, "slope_factor": 0.65},
    "Legazpi City":                 {"lat": 13.1391, "lon": 123.7438, "slope_factor": 0.70},
    "Batangas City":                {"lat": 13.7565, "lon": 121.0583, "slope_factor": 0.55},

    # Visayas
    "Iloilo City":                  {"lat": 10.7202, "lon": 122.5621, "slope_factor": 0.60},
    "Bacolod City":                 {"lat": 10.6407, "lon": 122.9689, "slope_factor": 0.55},
    "Cebu City":                    {"lat": 10.3157, "lon": 123.8854, "slope_factor": 0.70},
    "Tacloban City":                {"lat": 11.2543, "lon": 125.0000, "slope_factor": 0.60},

    # Mindanao
    "Cagayan de Oro City":          {"lat": 8.4822,  "lon": 124.6472, "slope_factor": 0.80},
    "Iligan City":                  {"lat": 8.2280,  "lon": 124.2452, "slope_factor": 0.78},
    "Davao City":                   {"lat": 7.1907,  "lon": 125.4553, "slope_factor": 0.55},
    "Zamboanga City":               {"lat": 6.9214,  "lon": 122.0790, "slope_factor": 0.50},
    "Cotabato City":                {"lat": 7.2231,  "lon": 124.2452, "slope_factor": 0.55},
    "General Santos City":         {"lat": 6.1164,  "lon": 125.1716, "slope_factor": 0.50},
    "Butuan City":                  {"lat": 8.9475,  "lon": 125.5406, "slope_factor": 0.65},

    # Palawan / MIMAROPA
    "Puerto Princesa City":         {"lat": 9.7392,  "lon": 118.7353, "slope_factor": 0.45},
}


WEATHER_API_URL = "https://api.open-meteo.com/v1/forecast"
ELEVATION_API_URL = "https://api.open-meteo.com/v1/elevation"
GEOCODING_API_URL = "https://geocoding-api.open-meteo.com/v1/search"

DEFAULT_SLOPE_FACTOR = 0.60

RISK_LEVELS = [
    (0, 25,  "LOW",      "#2ecc71"),
    (25, 50, "MODERATE", "#f1c40f"),
    (50, 75, "HIGH",     "#e67e22"),
    (75, 101, "CRITICAL", "#e74c3c"),
]

REFRESH_INTERVAL_MS = 60_000  # 60 seconds

SIM_STEPS = 400
SIM_DT = 0.01
LYAPUNOV_EPSILON = 1e-5  # initial separation between twin trajectories
