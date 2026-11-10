"""Flash Flood Risk Index dashboard (Streamlit)."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

from chaos_model import run_chaos_simulation, project_risk_timeseries
from config import (CACHE_TTL_SECONDS, LOCATIONS, MAP_CENTER, MAP_ZOOM)
from data_fetcher import fetch_weather
from gis_utils import build_hazard_map

st.set_page_config(page_title="Flash Flood Risk Index", page_icon="🌧️", layout="wide")


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def get_weather(lat, lon):
    return fetch_weather(lat, lon)


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def analyze(name):
    loc = LOCATIONS[name]
    weather = get_weather(loc["lat"], loc["lon"])
    sim = run_chaos_simulation(weather, loc["slope"])
    projection = project_risk_timeseries(
        sim["ffri"], weather["hourly_precip"], weather["soil_moisture"]
    )
    return weather, sim, projection


st.title("🌧️ Flash Flood Risk Index")
st.caption("Chaos-based (Lorenz) flash flood risk estimate using live Open-Meteo weather data.")

with st.sidebar:
    st.header("Settings")
    selected = st.multiselect("Locations", list(LOCATIONS), default=list(LOCATIONS))
    focus = st.selectbox("Detailed view", selected) if selected else None
    if st.button("🔄 Refresh data"):
        st.cache_data.clear()
        st.rerun()
    st.markdown("**Note:** Experimental model for learning purposes only. "
                "Not an official warning. Follow PAGASA advisories.")

if not selected:
    st.info("Pumili ng kahit isang location sa sidebar.")
    st.stop()

results, errors = {}, {}
with st.spinner("Kumukuha ng weather data..."):
    for name in selected:
        try:
            weather, sim, projection = analyze(name)
            results[name] = {
                "lat": LOCATIONS[name]["lat"], "lon": LOCATIONS[name]["lon"],
                "ffri": sim["ffri"], "risk_label": sim["risk_label"],
                "risk_color": sim["risk_color"], "elevation": weather["elevation"],
                "weather": weather, "sim": sim, "projection": projection,
            }
        except Exception as e:  # network or API errors
            errors[name] = str(e)

for name, err in errors.items():
    st.warning(f"{name}: hindi makuha ang data ({err})")

if not results:
    st.error("Walang nakuhang data. Subukan ulit mamaya.")
    st.stop()

# --- Map ---
st.subheader("Hazard Map")
fmap = build_hazard_map(results, center=MAP_CENTER, zoom_start=MAP_ZOOM)
components.html(fmap.get_root().render(), height=560)

# --- Summary table ---
st.subheader("Summary")
df = pd.DataFrame([
    {
        "Location": n,
        "FFRI": round(r["ffri"], 1),
        "Risk": r["risk_label"],
        "Rain (mm/hr)": r["weather"]["precipitation_mm"],
        "24h Rain (mm)": round(r["weather"]["precip_accum_24h_mm"], 1),
        "Soil moisture": round(r["weather"]["soil_moisture"], 2),
        "Elevation (m)": round(r["elevation"]),
    }
    for n, r in results.items()
]).sort_values("FFRI", ascending=False)
st.dataframe(df, use_container_width=True, hide_index=True)

# --- Detail view ---
if focus in results:
    r = results[focus]
    sim, weather = r["sim"], r["weather"]
    st.subheader(f"Detalye: {focus}")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("FFRI", f"{sim['ffri']:.1f} / 100")
    c2.metric("Risk level", sim["risk_label"])
    c3.metric("Lyapunov estimate", f"{sim['lyapunov_estimate']:.2f}")
    c4.metric("24h rainfall", f"{weather['precip_accum_24h_mm']:.1f} mm")

    left, right = st.columns(2)

    with left:
        st.markdown("**Risk projection (susunod na oras)**")
        hours = list(range(1, len(r["projection"]) + 1))
        fig = go.Figure(go.Scatter(x=hours, y=r["projection"], mode="lines+markers",
                                   line=dict(color=r["risk_color"], width=3)))
        fig.update_layout(xaxis_title="Hours ahead", yaxis_title="FFRI",
                          yaxis=dict(range=[0, 100]), height=380, margin=dict(t=10))
        st.plotly_chart(fig, use_container_width=True)

    with right:
        st.markdown("**Lorenz trajectory**")
        traj = sim["trajectory"]
        fig3d = go.Figure(go.Scatter3d(
            x=traj[:, 0], y=traj[:, 1], z=traj[:, 2], mode="lines",
            line=dict(color=sim["time"], colorscale="Viridis", width=3)))
        fig3d.update_layout(height=380, margin=dict(t=10, l=0, r=0, b=0))
        st.plotly_chart(fig3d, use_container_width=True)

    st.markdown("**Mga signal na bumubuo sa FFRI**")
    signals = pd.DataFrame({
        "Signal": ["Chaos (40%)", "Rainfall (30%)", "Soil saturation (20%)", "Terrain (10%)"],
        "Value": [sim["chaos_signal"], sim["rainfall_signal"],
                  sim["saturation_signal"], sim["terrain_signal"]],
    })
    st.bar_chart(signals, x="Signal", y="Value")

    st.caption(f"Lorenz params: σ={sim['sigma']:.2f}, ρ={sim['rho']:.2f}, β={sim['beta']:.2f} "
               f"· Data as of {weather['fetched_at']}")
