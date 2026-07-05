"""
app.py
------
GIS-Integrated Hybrid Chaos Theory-Based Flash Flood Early Warning System.
Main Streamlit dashboard: ingests live weather data, runs the hybrid chaos
model, and renders an interactive Web-GIS early warning interface.

Run with:
    streamlit run app.py
"""

import time
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components
from streamlit_autorefresh import st_autorefresh

from config import LOCATIONS, REFRESH_INTERVAL_MS, DEFAULT_SLOPE_FACTOR
from data_fetcher import (
    fetch_current_weather_batch, fetch_elevation_batch, generate_demo_weather, geocode_location,
    fetch_psgc_regions, get_provinces_for_region, get_places_for_province,
    get_independent_cities_for_region, clean_place_name, fetch_barangays_for_place,
)
from chaos_model import run_chaos_simulation, project_risk_timeseries
from gis_utils import build_hazard_map


# ============================================================================
# PAGE CONFIG + STYLING
# ============================================================================
st.set_page_config(
    page_title="Flash Flood EWS | Chaos-GIS Dashboard",
    page_icon="🌊",
    layout="wide",
    initial_sidebar_state="expanded",
)

CUSTOM_CSS = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@500;700&display=swap');

    :root {
        --water-cyan: #22d3ee;
        --water-blue: #3b82f6;
        --water-deep: #0b1220;
        --glass-bg: rgba(255, 255, 255, 0.045);
        --glass-border: rgba(148, 197, 255, 0.14);
        --glass-border-hover: rgba(34, 211, 238, 0.35);
    }

    /* ---------- animated ambient background ---------- */
    .stApp {
        background:
            radial-gradient(circle at 12% 8%, rgba(34, 211, 238, 0.10), transparent 40%),
            radial-gradient(circle at 88% 18%, rgba(59, 130, 246, 0.10), transparent 45%),
            radial-gradient(circle at 50% 100%, rgba(34, 211, 238, 0.06), transparent 50%),
            var(--water-deep);
        background-size: 200% 200%, 200% 200%, 200% 200%, 100% 100%;
        animation: driftMesh 26s ease-in-out infinite;
    }
    @keyframes driftMesh {
        0%   { background-position: 0% 0%, 100% 0%, 50% 100%, 0 0; }
        50%  { background-position: 30% 20%, 70% 30%, 60% 80%, 0 0; }
        100% { background-position: 0% 0%, 100% 0%, 50% 100%, 0 0; }
    }

    .main { background-color: transparent; }
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header[data-testid="stHeader"] { background: transparent; }

    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    h1, h2, h3 { font-family: 'Space Grotesk', sans-serif !important; }

    /* fade-in the whole page on load */
    .block-container {
        animation: fadeInUp 0.6s ease both;
        padding-top: 1.6rem;
    }
    @keyframes fadeInUp {
        from { opacity: 0; }
        to   { opacity: 1; }
    }

    /* ---------- title + ripple divider ---------- */
    h1 {
        background: linear-gradient(90deg, #f0f6fc, var(--water-cyan) 60%, var(--water-blue));
        -webkit-background-clip: text;
        background-clip: text;
        color: transparent;
        font-weight: 700 !important;
    }
    .wave-divider {
        height: 3px;
        margin: 10px 0 16px 0;
        border-radius: 999px;
        background: linear-gradient(90deg, var(--water-cyan), var(--water-blue), var(--water-cyan));
        background-size: 200% 100%;
        animation: waveFlow 4s linear infinite;
        opacity: 0.8;
    }
    @keyframes waveFlow {
        0% { background-position: 0% 50%; }
        100% { background-position: 200% 50%; }
    }

    /* ---------- glass metric cards ---------- */
    .metric-card {
        background: var(--glass-bg);
        backdrop-filter: blur(14px);
        -webkit-backdrop-filter: blur(14px);
        border: 1px solid var(--glass-border);
        border-radius: 16px;
        padding: 16px 18px;
        text-align: center;
        position: relative;
        overflow: hidden;
        transition: transform 0.25s ease, border-color 0.25s ease, box-shadow 0.25s ease;
        animation: fadeInUp 0.5s ease both;
    }
    .metric-card::before {
        content: "";
        position: absolute;
        top: 0; left: 0; right: 0;
        height: 2px;
        background: linear-gradient(90deg, var(--water-cyan), var(--water-blue));
        opacity: 0.7;
    }
    .metric-card:hover {
        transform: translateY(-4px);
        border-color: var(--glass-border-hover);
        box-shadow: 0 10px 30px -10px rgba(34, 211, 238, 0.25);
    }
    .metric-card h3 { margin: 0; font-size: 12.5px; color: #8b949e; font-weight: 500; letter-spacing: 0.3px; text-transform: uppercase; }
    .metric-card p {
        margin: 6px 0 0 0;
        font-size: 26px;
        font-weight: 700;
        color: #f0f6fc;
        font-family: 'JetBrains Mono', monospace;
    }

    /* ---------- risk banner with pulsing glow ---------- */
    .risk-banner {
        border-radius: 16px;
        padding: 22px;
        text-align: center;
        color: white;
        font-weight: 800;
        font-size: 22px;
        letter-spacing: 1px;
        margin-bottom: 6px;
        backdrop-filter: blur(14px);
        -webkit-backdrop-filter: blur(14px);
        position: relative;
        animation: bannerPulse 2.6s ease-in-out infinite, fadeInUp 0.5s ease both;
    }
    @keyframes bannerPulse {
        0%, 100% { box-shadow: 0 0 0px 0px rgba(255,255,255,0.0), 0 8px 30px -12px rgba(0,0,0,0.5); }
        50%      { box-shadow: 0 0 24px 2px var(--banner-glow, rgba(255,255,255,0.3)), 0 8px 30px -12px rgba(0,0,0,0.5); }
    }

    .subtle { color: #8b949e; font-size: 13px; }

    /* ---------- section titles ---------- */
    .section-title {
        font-size: 18px;
        font-weight: 700;
        color: #f0f6fc;
        margin: 22px 0 10px 0;
        padding-left: 12px;
        position: relative;
        font-family: 'Space Grotesk', sans-serif;
    }
    .section-title::before {
        content: "";
        position: absolute;
        left: 0; top: 2px; bottom: 2px;
        width: 4px;
        border-radius: 4px;
        background: linear-gradient(180deg, var(--water-cyan), var(--water-blue));
        box-shadow: 0 0 8px rgba(34, 211, 238, 0.6);
    }

    /* ---------- glass panels around map + charts ---------- */
    [data-testid="stIFrame"], [data-testid="stPlotlyChart"] {
        border-radius: 16px !important;
        overflow: hidden;
        background: var(--glass-bg);
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
        border: 1px solid var(--glass-border);
        transition: border-color 0.25s ease, box-shadow 0.25s ease;
    }
    [data-testid="stIFrame"]:hover, [data-testid="stPlotlyChart"]:hover {
        border-color: var(--glass-border-hover);
        box-shadow: 0 12px 34px -14px rgba(34, 211, 238, 0.25);
    }

    /* ---------- sidebar ---------- */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, rgba(15, 23, 42, 0.92), rgba(11, 18, 32, 0.96));
        border-right: 1px solid var(--glass-border);
    }
    section[data-testid="stSidebar"] h2, section[data-testid="stSidebar"] h3 {
        background: linear-gradient(90deg, var(--water-cyan), var(--water-blue));
        -webkit-background-clip: text;
        background-clip: text;
        color: transparent;
    }

    /* ---------- inputs, buttons, tabs ---------- */
    .stButton > button {
        background: linear-gradient(135deg, rgba(34,211,238,0.16), rgba(59,130,246,0.16));
        border: 1px solid var(--glass-border);
        color: #f0f6fc;
        border-radius: 10px;
        transition: all 0.2s ease;
    }
    .stButton > button:hover {
        border-color: var(--water-cyan);
        box-shadow: 0 0 16px rgba(34, 211, 238, 0.35);
        transform: translateY(-1px);
    }

    div[data-baseweb="select"] > div,
    .stTextInput > div > div,
    [data-testid="stNumberInput"] input {
        background: var(--glass-bg) !important;
        border-color: var(--glass-border) !important;
        border-radius: 10px !important;
    }

    .stTabs [data-baseweb="tab-list"] { gap: 6px; }
    .stTabs [data-baseweb="tab"] {
        background: var(--glass-bg);
        border: 1px solid var(--glass-border);
        border-radius: 10px 10px 0 0;
        color: #8b949e;
    }
    .stTabs [aria-selected="true"] {
        color: var(--water-cyan) !important;
        border-color: var(--glass-border-hover) !important;
    }

    /* thin, glowing scrollbar */
    ::-webkit-scrollbar { width: 8px; height: 8px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb {
        background: linear-gradient(180deg, var(--water-cyan), var(--water-blue));
        border-radius: 8px;
    }

    /* respect reduced motion preferences */
    @media (prefers-reduced-motion: reduce) {
        .stApp, .risk-banner, .metric-card, .wave-divider, .block-container {
            animation: none !important;
        }
    }

    /* ---------- mobile: disable backdrop-filter on iframe/chart wrappers ----------
       backdrop-filter + iframes has a well-known repaint bug on mobile Safari/
       Chrome: the blurred layer can get "stuck" showing a stale blank/black
       frame until something forces a reflow (e.g. opening DevTools). It's a
       purely decorative effect, so we just turn it off below ~768px instead
       of fighting the browser bug. */
    @media (max-width: 768px) {
        [data-testid="stIFrame"], [data-testid="stPlotlyChart"] {
            backdrop-filter: none !important;
            -webkit-backdrop-filter: none !important;
            background: rgba(11, 18, 32, 0.55) !important;
        }
        /* Force the folium map's own iframe box to a sane, fixed height on
           mobile — some streamlit-folium versions mis-calculate height when
           combined with use_container_width on narrow viewports, reserving
           far more vertical space than intended. */
        [data-testid="stIFrame"] iframe {
            width: 100% !important;
            height: 460px !important;
            max-height: 460px !important;
        }
        [data-testid="stIFrame"] {
            height: 460px !important;
            max-height: 460px !important;
            overflow: hidden !important;
        }
    }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# ============================================================================
# SIDEBAR — CONTROLS
# ============================================================================
with st.sidebar:
    st.markdown("## 🌊 Flood EWS Control Panel")
    st.caption("GIS-Integrated Hybrid Chaos-Theory Flash Flood Prediction")

    # Custom, user-added locations persist for the session
    if "custom_locations" not in st.session_state:
        st.session_state.custom_locations = {}

    st.markdown("---")
    st.markdown("#### 📍 Add a monitoring location")
    tab_browse, tab_search = st.tabs(["🗂️ Browse all PH cities", "🔎 Search by name"])

    with tab_browse:
        regions = fetch_psgc_regions()
        if not regions:
            st.caption("⚠️ Couldn't reach the PSGC directory right now. Try the Search tab instead.")
        else:
            region_options = {r["name"]: r["code"] for r in sorted(regions, key=lambda r: r["name"])}
            region_name = st.selectbox("Region", options=list(region_options.keys()), key="region_pick")
            region_code = region_options[region_name]

            provinces = get_provinces_for_region(region_code)
            independent_cities = get_independent_cities_for_region(region_code)

            province_options = {"— (none / independent cities below) —": None}
            province_options.update({p["name"]: p["code"] for p in provinces})
            province_name = st.selectbox("Province", options=list(province_options.keys()), key="province_pick")
            province_code = province_options[province_name]

            if province_code:
                places = get_places_for_province(province_code)
            else:
                places = independent_cities

            if places:
                place_labels = {clean_place_name(p["name"]): p for p in places}
                place_pick = st.selectbox(
                    f"City / Municipality ({len(places)} found)",
                    options=list(place_labels.keys()),
                    key="place_pick",
                )
                selected_place = place_labels[place_pick]

                barangays = fetch_barangays_for_place(selected_place.get("code", ""))
                barangay_pick = None
                if barangays:
                    barangay_options = ["— (whole city/municipality) —"] + [b["name"] for b in barangays]
                    barangay_pick = st.selectbox(
                        f"Barangay ({len(barangays)} found)",
                        options=barangay_options,
                        key="barangay_pick",
                    )
                    if barangay_pick == barangay_options[0]:
                        barangay_pick = None
                else:
                    st.caption("No barangay list available for this place — will monitor at city/municipality level.")

                if st.button("➕ Add to monitoring", key="add_browse", use_container_width=True):
                    qualifier = province_name if province_code else region_name

                    # Multi-step fallback: barangay+place first (most precise),
                    # then place alone, then place+qualifier — since exact
                    # spellings don't always match the geocoding database.
                    geo_matches = None
                    if barangay_pick:
                        geo_matches = geocode_location(f"{barangay_pick}, {place_pick}")
                    if not geo_matches:
                        geo_matches = geocode_location(place_pick)
                    if not geo_matches:
                        geo_matches = geocode_location(f"{place_pick} {qualifier}")

                    if geo_matches:
                        best = geo_matches[0]
                        location_label = f"{barangay_pick}, {place_pick}" if barangay_pick else place_pick
                        display_name = f"{location_label}, {qualifier}"
                        st.session_state.custom_locations[display_name] = {
                            "lat": best["lat"], "lon": best["lon"], "slope_factor": DEFAULT_SLOPE_FACTOR,
                        }
                        st.success(f"Added {display_name}")
                        st.rerun()
                    else:
                        st.warning("Couldn't find coordinates for that place. Try the Search tab instead.")
            else:
                st.caption("No independent cities directly under this region — pick a province above.")

    with tab_search:
        search_query = st.text_input("Search city/municipality", placeholder="e.g. Malolos, Bulacan")
        if st.button("Search", use_container_width=True) and search_query.strip():
            st.session_state.search_results = geocode_location(search_query.strip())

        if st.session_state.get("search_results"):
            options = {m["name"]: m for m in st.session_state.search_results}
            picked = st.selectbox("Matches found", options=list(options.keys()), key="picked_match")
            if st.button("➕ Add to monitoring", key="add_search", use_container_width=True):
                match = options[picked]
                st.session_state.custom_locations[match["name"]] = {
                    "lat": match["lat"], "lon": match["lon"], "slope_factor": DEFAULT_SLOPE_FACTOR,
                }
                st.session_state.search_results = []
                st.rerun()

    # Merge built-in + user-added locations
    all_locations_config = {**LOCATIONS, **st.session_state.custom_locations}

    if st.session_state.custom_locations:
        st.caption(f"📍 {len(st.session_state.custom_locations)} custom location(s) added this session")

    st.markdown("---")
    selected_location = st.selectbox(
        "📍 Monitoring Site",
        options=list(all_locations_config.keys()),
        index=0,
    )

    st.markdown("---")
    demo_mode = st.toggle("🧪 Offline demo mode (simulated data)", value=False,
                          help="Use this if there's no internet during a presentation/defense. "
                               "Generates plausible simulated weather instead of calling the live API.")

    st.markdown("---")
    auto_refresh = st.toggle("🔄 Live auto-refresh", value=True)
    refresh_secs = st.slider("Refresh interval (seconds)", 15, 180, int(REFRESH_INTERVAL_MS / 1000))

    if st.button("↻ Refresh now", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.markdown("---")
    st.markdown("#### ⚙️ About this model")
    st.caption(
        "Real-time weather (rainfall, humidity, soil moisture) drives a "
        "modified Lorenz chaos system. The rate at which twin trajectories "
        "diverge (sensitivity to initial conditions) is used as a proxy for "
        "hydrological instability, then combined with rainfall accumulation "
        "and terrain data into a 0–100 Flash Flood Risk Index."
    )

if auto_refresh:
    st_autorefresh(interval=refresh_secs * 1000, key="auto_refresh_timer")


# ============================================================================
# DATA INGESTION — run chaos model for ALL locations (for the GIS map)
# ============================================================================
@st.cache_data(ttl=60)
def compute_all_locations(use_demo: bool, locations_dict: dict):
    coords = tuple((meta["lat"], meta["lon"]) for meta in locations_dict.values())

    if use_demo:
        weather_by_coord = {c: generate_demo_weather(*c) for c in coords}
        elevation_by_coord = {c: 50.0 for c in coords}
    else:
        weather_by_coord = fetch_current_weather_batch(coords)
        elevation_by_coord = fetch_elevation_batch(coords)

    results = {}
    for name, meta in locations_dict.items():
        coord = (meta["lat"], meta["lon"])
        weather = weather_by_coord.get(coord, generate_demo_weather(*coord))
        elevation = elevation_by_coord.get(coord, 0.0)

        sim = run_chaos_simulation(weather, slope_factor=meta["slope_factor"])
        results[name] = {
            "lat": meta["lat"],
            "lon": meta["lon"],
            "elevation": elevation,
            "weather": weather,
            **sim,
        }
    return results


all_results = compute_all_locations(demo_mode, all_locations_config)
site = all_locations_config[selected_location]
result = all_results[selected_location]
weather = result["weather"]


# ============================================================================
# HEADER
# ============================================================================
st.markdown(
    "<h1 style='margin-bottom:0;'>🌊 Automated Flash Flood Early Warning System</h1>"
    "<p class='subtle'>GIS-Integrated Hybrid Chaos Theory-Based Predictive Modeling "
    "of Localized Flash Flood Risk Using Real-Time Weather and Spatial Data</p>"
    "<div class='wave-divider'></div>",
    unsafe_allow_html=True,
)
st.caption(f"Last updated: {time.strftime('%Y-%m-%d %H:%M:%S')} · Site: **{selected_location}**")

if weather.get("demo_mode"):
    st.info("🧪 Running in **Offline Demo Mode** — weather values are simulated, not live data.")
elif not weather.get("success", True):
    st.warning(f"⚠️ Live weather API issue for this session, showing fallback values. ({weather.get('error')})")


# ============================================================================
# ALERT BANNER
# ============================================================================
st.markdown(
    f"""<div class="risk-banner" style="background:{result['risk_color']}22;
        border:2px solid {result['risk_color']}; --banner-glow:{result['risk_color']};">
        <span style="color:{result['risk_color']}">⚠ {result['risk_label']} FLASH FLOOD RISK</span>
        &nbsp;—&nbsp; Flash Flood Risk Index: {result['ffri']:.1f} / 100
    </div>""",
    unsafe_allow_html=True,
)


# ============================================================================
# METRIC CARDS
# ============================================================================
cols = st.columns(6)
metrics = [
    ("🌧 Rainfall", f"{weather['rain_mm']:.1f} mm"),
    ("💧 24h Accum.", f"{weather['precip_accum_24h_mm']:.1f} mm"),
    ("🌫 Humidity", f"{weather['humidity_pct']:.0f}%"),
    ("🌡 Temp", f"{weather['temperature_c']:.1f}°C"),
    ("🟤 Soil Moisture", f"{weather['soil_moisture']:.2f}"),
    ("⛰ Elevation", f"{result['elevation']:.0f} m"),
]
for c, (label, value) in zip(cols, metrics):
    c.markdown(f"<div class='metric-card'><h3>{label}</h3><p>{value}</p></div>", unsafe_allow_html=True)


# ============================================================================
# MAIN LAYOUT: MAP + CHAOS VISUALS
# ============================================================================
st.markdown("<div class='section-title'>🗺️ Web-GIS Regional Hazard Map</div>", unsafe_allow_html=True)
hazard_map = build_hazard_map(all_results)
components.html(hazard_map._repr_html_(), height=460, scrolling=False)

left, right = st.columns([1.1, 1])

with left:
    st.markdown("<div class='section-title'>🌀 Chaos Attractor (Lorenz Phase Space)</div>", unsafe_allow_html=True)
    traj = result["trajectory"]
    fig_attractor = go.Figure(
        data=[
            go.Scatter3d(
                x=traj[:, 0], y=traj[:, 1], z=traj[:, 2],
                mode="lines",
                line=dict(color=np.linspace(0, 1, len(traj)), colorscale="Turbo", width=3),
            )
        ]
    )
    fig_attractor.update_layout(
        margin=dict(l=0, r=0, t=10, b=0),
        height=380,
        scene=dict(
            xaxis=dict(visible=False), yaxis=dict(visible=False), zaxis=dict(visible=False),
            bgcolor="rgba(0,0,0,0)",
        ),
        paper_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig_attractor, use_container_width=True)
    st.caption(
        f"σ={result['sigma']:.2f} · ρ={result['rho']:.2f} · β={result['beta']:.2f} · "
        f"Lyapunov estimate ≈ {result['lyapunov_estimate']:.3f}"
    )

with right:
    st.markdown("<div class='section-title'>📊 Risk Index Gauge</div>", unsafe_allow_html=True)
    fig_gauge = go.Figure(go.Indicator(
        mode="gauge+number",
        value=result["ffri"],
        number={"suffix": " / 100"},
        gauge={
            "axis": {"range": [0, 100]},
            "bar": {"color": result["risk_color"]},
            "steps": [
                {"range": [0, 25], "color": "#1f5c39"},
                {"range": [25, 50], "color": "#5c5320"},
                {"range": [50, 75], "color": "#5c3a1a"},
                {"range": [75, 100], "color": "#5c1f1f"},
            ],
        },
    ))
    fig_gauge.update_layout(height=280, margin=dict(l=20, r=20, t=20, b=10), paper_bgcolor="rgba(0,0,0,0)", font=dict(color="#f0f6fc"))
    st.plotly_chart(fig_gauge, use_container_width=True)

    st.markdown("<div class='section-title' style='margin-top:0'>🧬 Contributing Signals</div>", unsafe_allow_html=True)
    signal_df = pd.DataFrame({
        "Signal": ["Chaos Instability", "Rainfall", "Soil Saturation", "Terrain Vulnerability"],
        "Value": [result["chaos_signal"], result["rainfall_signal"], result["saturation_signal"], result["terrain_signal"]],
    })
    fig_signals = go.Figure(go.Bar(
        x=signal_df["Value"], y=signal_df["Signal"], orientation="h",
        marker_color=["#3b82f6", "#22c55e", "#a855f7", "#f97316"],
    ))
    fig_signals.update_layout(
        height=200, margin=dict(l=10, r=10, t=10, b=10),
        xaxis=dict(range=[0, 1], color="#8b949e"), yaxis=dict(color="#f0f6fc"),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig_signals, use_container_width=True)


# ============================================================================
# FORECAST TIMELINE
# ============================================================================
st.markdown("<div class='section-title'>⏱️ Projected Risk — Next 24 Hours</div>", unsafe_allow_html=True)
projected = project_risk_timeseries(
    result["ffri"], weather.get("hourly_precip_series", []), weather["soil_moisture"]
)
hours = list(range(1, len(projected) + 1))
fig_forecast = go.Figure()
fig_forecast.add_trace(go.Scatter(
    x=hours, y=projected, mode="lines+markers", name="Projected FFRI",
    line=dict(color="#3b82f6", width=3), fill="tozeroy", fillcolor="rgba(59,130,246,0.15)",
))
fig_forecast.add_hline(y=75, line_dash="dash", line_color="#e74c3c", annotation_text="Critical")
fig_forecast.add_hline(y=50, line_dash="dash", line_color="#e67e22", annotation_text="High")
fig_forecast.add_hline(y=25, line_dash="dash", line_color="#f1c40f", annotation_text="Moderate")
fig_forecast.update_layout(
    height=320, margin=dict(l=10, r=10, t=10, b=10),
    xaxis_title="Hours ahead", yaxis=dict(title="Flash Flood Risk Index", range=[0, 100]),
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#f0f6fc"),
)
st.plotly_chart(fig_forecast, use_container_width=True)

st.markdown(
    "<p class='subtle'>Prototype for research purposes. Weather data: Open-Meteo API. "
    "Chaos model: hybrid weather-driven Lorenz system. Not for operational emergency use.</p>",
    unsafe_allow_html=True,
)
