"""Automated Flash Flood Early Warning System - Streamlit dashboard."""
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

import ph_locations as ph
from chaos_model import project_risk_timeseries, run_chaos_simulation
from config import DEFAULT_SITE, MAP_CENTER, MAP_REFRESH_SECONDS, MAP_ZOOM, PRESET_SITES
from data_fetcher import SCENARIOS, fetch_weather, simulate_weather
from gis_utils import build_hazard_map
from terrain import get_terrain

st.set_page_config(page_title="Flash Flood EWS — Chaos-GIS Dashboard",
                   page_icon="🌊", layout="wide")

# ----------------------------------------------------------------- styling
st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&family=JetBrains+Mono:wght@500;700&display=swap');
html, body, [class*="css"], .stMarkdown { font-family: 'Space Grotesk', sans-serif; }
.stApp { background: radial-gradient(ellipse at 50% 0%, #10283b 0%, #08121c 55%); }
[data-testid="stSidebar"] { background: #0a1722; border-right: 1px solid rgba(255,255,255,.06); }
.block-container { padding-top: 2.5rem; max-width: 1100px; }
.side-title { font-size: 1.25rem; font-weight: 700; color: #22d3ee; margin-top: .5rem; }
.side-sub { color: #8aa0b4; font-size: .85rem; margin-top: .3rem; }
.app-title { font-size: 2.6rem; font-weight: 700; line-height: 1.15; margin: 0; }
.app-title .grad { background: linear-gradient(90deg,#ffffff 0%,#22d3ee 55%,#3b82f6 100%);
  -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent; }
.app-sub { color: #9fb3c8; font-size: .8rem; margin: .8rem 0 1rem; }
.rule { height: 2px; background: linear-gradient(90deg,#22d3ee,#3b82f6 60%,transparent); margin-bottom: .8rem; }
.updated { color: #9fb3c8; font-size: .8rem; margin-bottom: 1rem; }
.banner { border: 2px solid var(--c); background: color-mix(in srgb, var(--c) 10%, transparent);
  border-radius: 12px; padding: 1rem 1.2rem; text-align: center; font-size: 1.15rem; margin-bottom: 1rem; }
.banner .lvl { color: var(--c); font-weight: 700; letter-spacing: .02em; }
.banner .idx { font-weight: 700; color: #fff; }
.cards { display: grid; grid-template-columns: repeat(6, 1fr); gap: .6rem; margin-bottom: 1.6rem; }
.card { background: rgba(255,255,255,.04); border: 1px solid rgba(255,255,255,.08); border-radius: 14px;
  padding: .9rem .6rem; text-align: center; }
.card .lbl { font-size: .68rem; color: #9fb3c8; letter-spacing: .06em; text-transform: uppercase; min-height: 2rem; }
.card .val { font-family: 'JetBrains Mono', monospace; font-weight: 700; font-size: 1.35rem; color: #f1f5f9; margin-top: .2rem; }
.sec { border-left: 3px solid #22d3ee; padding-left: .7rem; font-weight: 700; font-size: 1.1rem; margin: 1.2rem 0 .7rem; }
[data-testid="stPlotlyChart"] { background: rgba(255,255,255,.03); border: 1px solid rgba(255,255,255,.07);
  border-radius: 14px; padding: 6px; }
iframe { border-radius: 14px; border: 1px solid rgba(255,255,255,.08); }
.foot { color: #7f93a8; font-size: .75rem; margin-top: 1rem; }
@media (max-width: 900px) { .cards { grid-template-columns: repeat(3, 1fr); } .app-title { font-size: 1.8rem; } }
</style>""", unsafe_allow_html=True)


# ----------------------------------------------------------------- data
def _analyze_raw(lat, lon, offline, scenario):
    weather = simulate_weather(lat, lon, scenario) if offline else fetch_weather(lat, lon)
    terrain = get_terrain(lat, lon, offline)
    sim = run_chaos_simulation(weather, terrain["factor"])
    proj = project_risk_timeseries(sim["ffri"], weather["hourly_precip"], weather["soil_moisture"])
    return weather, sim, proj, terrain


@st.cache_data(show_spinner=False, max_entries=100)
def analyze(lat, lon, offline, scenario, bucket):
    return _analyze_raw(lat, lon, offline, scenario)


@st.cache_resource
def site_cache():
    """Persistent per-site results for the map. Only successes are stored."""
    return {}


def _map_entry(name, lat, lon, offline, scenario, ttl):
    cache = site_cache()
    key = (round(lat, 4), round(lon, 4), offline, scenario)
    now = time.time()
    hit = cache.get(key)
    if hit and now - hit[0] < ttl:
        return hit[1], None
    last = None
    for attempt in range(2):                      # one retry for transient API errors / rate limits
        try:
            w, s, _, _ = _analyze_raw(lat, lon, offline, scenario)
            entry = {"lat": lat, "lon": lon, "ffri": s["ffri"], "risk_label": s["risk_label"],
                     "risk_color": s["risk_color"], "elevation": w["elevation"]}
            cache[key] = (now, entry)
            return entry, None
        except Exception as e:
            last = e
            time.sleep(1.5)
    return None, f"{type(last).__name__}: {last}"[:90]


def collect_map_results(sites: dict, offline, scenario):
    items = [(n, s["lat"], s["lon"]) for n, s in sites.items()]
    with ThreadPoolExecutor(max_workers=6) as ex:
        out = list(ex.map(lambda it: (it[0], *_map_entry(it[0], it[1], it[2], offline, scenario, MAP_REFRESH_SECONDS)), items))
    results = {n: r for n, r, _ in out if r}
    failed = {n: err for n, r, err in out if not r}
    return results, failed


@st.cache_data(ttl=86400, show_spinner=False)
def load_regions(): return ph.get_regions()
@st.cache_data(ttl=86400, show_spinner=False)
def load_provinces(c): return ph.get_provinces(c)
@st.cache_data(ttl=86400, show_spinner=False)
def load_region_cities(c): return ph.get_region_cities(c)
@st.cache_data(ttl=86400, show_spinner=False)
def load_province_cities(c): return ph.get_province_cities(c)
@st.cache_data(ttl=86400, show_spinner=False)
def load_barangays(c): return ph.get_barangays(c)
@st.cache_data(ttl=3600, show_spinner=False)
def search_places(q): return ph.geocode(q, count=8)


def pick(label, options, key):
    """Selectbox over a list of {'code','name'} dicts; returns the chosen dict."""
    names = {o["code"]: o["name"] for o in options}
    code = st.selectbox(label, list(names), format_func=names.get, key=key)
    return next(o for o in options if o["code"] == code)



def show_chart(fig):
    """plotly chart, full width, on both old and new Streamlit versions."""
    try:
        st.plotly_chart(fig, width="stretch")
    except TypeError:
        show_chart(fig)


def wide_button(label, key):
    try:
        return st.button(label, width="stretch", key=key)
    except TypeError:
        return st.button(label, use_container_width=True, key=key)


# ----------------------------------------------------------------- state
st.session_state.setdefault("custom_sites", {})
st.session_state.setdefault("site_select", DEFAULT_SITE)


def add_custom(label, lat, lon, precision):
    st.session_state.custom_sites[label] = {"lat": lat, "lon": lon, "precision": precision}
    st.session_state["site_select"] = label


# ----------------------------------------------------------------- sidebar
with st.sidebar:
    st.markdown('<div class="side-title">🌊 Flood EWS Control Panel</div>'
                '<div class="side-sub">GIS-Integrated Hybrid Chaos-Theory Flash Flood Prediction</div>',
                unsafe_allow_html=True)
    st.divider()
    st.markdown("##### 📍 Add a monitoring location")
    tab_browse, tab_search = st.tabs(["📁 Browse all PH cities", "🔎 Search by name"])

    with tab_browse:
        try:
            region = pick("Region", load_regions(), "region")
            provinces = load_provinces(region["code"])
            none_opt = {"code": "", "name": "— (none / independent cities by region)"}
            province = pick("Province", [none_opt] + provinces, f"prov_{region['code']}")
            cities = (load_province_cities(province["code"]) if province["code"]
                      else load_region_cities(region["code"]))
            if not cities:
                st.caption("No independent cities directly under this region — pick a province above.")
            else:
                city = pick(f"City / Municipality ({len(cities)} found)", cities, f"city_{province['code']}_{region['code']}")
                brgys = load_barangays(city["code"])
                brgy = pick(f"Barangay ({len(brgys)} found)", brgys, f"brgy_{city['code']}") if brgys else None
                if wide_button("➕ Add to monitoring", "add_browse"):
                    with st.spinner("Hinahanap ang coordinates..."):
                        try:
                            loc = ph.locate(brgy["name"] if brgy else None, city["name"], province["name"] if province["code"] else None)
                        except Exception as e:
                            loc = None
                            st.error(f"Geocoding error: {e}")
                    if loc:
                        parts = [brgy["name"] if brgy else None, city["name"],
                                 province["name"] if province["code"] else region["name"]]
                        add_custom(", ".join(p for p in parts if p), loc["lat"], loc["lon"], loc["precision"])
                    else:
                        st.warning("Hindi mahanap ang coordinates ng lugar na ito.")
        except Exception as e:
            st.warning(f"Hindi ma-load ang PH location list ({e}). Gamitin ang 'Search by name' o i-check ang internet.")

    with tab_search:
        q = st.text_input("Place name", placeholder="e.g. Calaitan, Bayugan", key="place_q")
        if q.strip():
            try:
                hits = search_places(q.strip())
            except Exception as e:
                hits, _ = [], st.warning(f"Search failed: {e}")
            if hits:
                labels = [", ".join(p for p in (h["name"], h["admin2"], h["admin1"]) if p) for h in hits]
                i = st.selectbox("Results", range(len(hits)), format_func=lambda i: labels[i], key="place_pick")
                if wide_button("➕ Add to monitoring", "add_search"):
                    add_custom(labels[i], hits[i]["lat"], hits[i]["lon"], "search")
            elif q.strip():
                st.caption("Walang nahanap na lugar.")

    n_custom = len(st.session_state.custom_sites)
    if n_custom:
        st.caption(f"📍 {n_custom} custom location(s) added this session")

    st.divider()
    sites = {n: {"lat": la, "lon": lo} for n, (la, lo) in PRESET_SITES.items()}
    sites.update(st.session_state.custom_sites)
    st.markdown("**📍 Monitoring Site**")
    site = st.selectbox("Monitoring Site", list(sites), key="site_select", label_visibility="collapsed")

    st.divider()
    offline = st.toggle("🧪 Offline demo mode (simulated data)", key="offline",
                        help="Gumagamit ng gawa-gawang weather data para gumana kahit walang internet.")
    scenario = "Heavy rain"
    if offline:
        scenario = st.selectbox("Demo scenario", list(SCENARIOS), index=1)

    st.divider()
    live = st.toggle("🔄 Live auto-refresh", value=True)
    interval = st.slider("Refresh interval (seconds)", 30, 600, 60, step=30, disabled=not live)
    if live:
        try:
            from streamlit_autorefresh import st_autorefresh
            st_autorefresh(interval=interval * 1000, key="auto_refresh")
        except ImportError:
            st.caption("I-install ang `streamlit-autorefresh` para gumana ang auto-refresh.")


# ----------------------------------------------------------------- analysis
sel = sites[site]
bucket = int(time.time() // (interval if live else 600))
try:
    weather, sim, proj, terrain = analyze(sel["lat"], sel["lon"], offline, scenario, bucket)
except Exception as e:
    st.error(f"Hindi makuha ang weather data para sa {site}: {e}\n\n"
             "I-check ang internet, o i-on ang **Offline demo mode** sa sidebar.")
    st.stop()

color, label, ffri = sim["risk_color"], sim["risk_label"], sim["ffri"]

# ----------------------------------------------------------------- header
st.markdown('<h1 class="app-title">🌊 <span class="grad">Automated Flash Flood Early Warning System</span></h1>'
            '<div class="app-sub">GIS-Integrated Hybrid Chaos Theory-Based Predictive Modeling of Localized '
            'Flash Flood Risk Using Real-Time Weather and Spatial Data</div><div class="rule"></div>',
            unsafe_allow_html=True)
sim_note = f" · <b>SIMULATED DATA ({scenario})</b>" if offline else ""
st.markdown(f'<div class="updated">Last updated: {datetime.now():%Y-%m-%d %H:%M:%S} · Site: <b>{site}</b>{sim_note}</div>',
            unsafe_allow_html=True)
st.markdown(f'<div class="banner" style="--c:{color}"><span class="lvl">⚠ {label} FLASH FLOOD RISK</span>'
            f' &nbsp;—&nbsp; <span class="idx">Flash Flood Risk Index: {ffri:.1f} / 100</span></div>',
            unsafe_allow_html=True)

rain_now = max(weather["rain_mm"], weather["precipitation_mm"])
cards = [("🌧️ Rainfall", f"{rain_now:.1f} mm"), ("💧 24H Accum.", f"{weather['precip_accum_24h_mm']:.1f} mm"),
         ("💨 Humidity", f"{weather['humidity_pct']:.0f}%"), ("🌡️ Temp", f"{weather['temp_c']:.1f}°C"),
         ("🌱 Soil Moisture", f"{weather['soil_moisture']:.2f}"), ("▲ Elevation", f"{weather['elevation']:.0f} m")]
st.markdown('<div class="cards">' + "".join(
    f'<div class="card"><div class="lbl">{l}</div><div class="val">{v}</div></div>' for l, v in cards) + '</div>',
    unsafe_allow_html=True)

# ----------------------------------------------------------------- map
st.markdown('<div class="sec">🗺️ Web-GIS Regional Hazard Map</div>', unsafe_allow_html=True)
with st.spinner("Kinukuha ang risk ng lahat ng monitoring sites..."):
    results, failed = collect_map_results(sites, offline, scenario)

# The selected site was already analysed above, so it must always appear on the map.
results[site] = {"lat": sel["lat"], "lon": sel["lon"], "ffri": ffri, "risk_label": label,
                 "risk_color": color, "elevation": weather["elevation"]}
failed.pop(site, None)

is_custom = site in st.session_state.custom_sites
center, zoom = ((sel["lat"], sel["lon"]), 9) if is_custom else (MAP_CENTER, MAP_ZOOM)
fmap = build_hazard_map(results, center=center, zoom_start=zoom)
components.html(fmap.get_root().render(), height=520)
if failed:
    st.caption("⚠️ Walang data para sa: " + "; ".join(f"{n} ({e})" for n, e in failed.items()))

# ----------------------------------------------------------------- attractor + gauge + signals
def attractor_fig(traj):
    chunks = 80
    step = max(len(traj) // chunks, 1)
    cols = px.colors.sample_colorscale("Turbo", [i / (chunks - 1) for i in range(chunks)])
    fig = go.Figure()
    for i in range(chunks):
        seg = traj[i * step: (i + 1) * step + 1]
        fig.add_trace(go.Scatter(x=seg[:, 0], y=seg[:, 1], mode="lines",
                                 line=dict(color=cols[i], width=2), showlegend=False, hoverinfo="skip"))
    fig.update_layout(height=420, margin=dict(l=10, r=10, t=10, b=10),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      xaxis=dict(visible=False), yaxis=dict(visible=False))
    return fig


def gauge_fig(value, bar_color):
    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=value,
        number={"suffix": " / 100", "valueformat": ".1f", "font": {"size": 44, "color": "#fff"}},
        gauge={"axis": {"range": [0, 100], "tickvals": [0, 20, 40, 60, 80, 100], "tickcolor": "#9fb3c8"},
               "bar": {"color": bar_color, "thickness": 0.28}, "bgcolor": "rgba(0,0,0,0)", "borderwidth": 0,
               "steps": [{"range": [0, 25], "color": "#1f6b3a"}, {"range": [25, 50], "color": "#6b6a1f"},
                         {"range": [50, 75], "color": "#6b3a1a"}, {"range": [75, 100], "color": "#5a1c1c"}]}))
    fig.update_layout(height=250, margin=dict(l=30, r=30, t=30, b=10), paper_bgcolor="rgba(0,0,0,0)",
                      font={"color": "#cbd5e1"})
    return fig


def signals_fig(s):
    fig = go.Figure(go.Bar(
        x=[s["chaos_signal"], s["rainfall_signal"], s["saturation_signal"], s["terrain_signal"]],
        y=["Chaos Instability", "Rainfall", "Soil Saturation", "Terrain Vulnerability"], orientation="h",
        marker_color=["#ef4444", "#2ecc71", "#a855f7", "#f97316"]))
    fig.update_layout(height=230, margin=dict(l=10, r=20, t=10, b=30), xaxis=dict(range=[0, 1]),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font={"color": "#cbd5e1"})
    fig.update_xaxes(gridcolor="rgba(255,255,255,.08)")
    return fig


left, right = st.columns([1.1, 1])
with left:
    st.markdown('<div class="sec">🌀 Chaos Attractor (Lorenz Phase Space)</div>', unsafe_allow_html=True)
    show_chart(attractor_fig(sim["trajectory"]))
    st.caption(f"σ={sim['sigma']:.2f} · ρ={sim['rho']:.2f} · β={sim['beta']:.2f} · "
               f"Lyapunov estimate ≈ {sim['lyapunov_estimate']:.3f}")
with right:
    st.markdown('<div class="sec">📊 Risk Index Gauge</div>', unsafe_allow_html=True)
    show_chart(gauge_fig(ffri, color))
    st.markdown('<div class="sec">🧬 Contributing Signals</div>', unsafe_allow_html=True)
    show_chart(signals_fig(sim))
    st.caption(f"Terrain: slope {terrain['slope_deg']:.1f}° · "
               f"{terrain['relief_m']:+.0f} m vs. surroundings · source: {terrain['source']}")

# ----------------------------------------------------------------- projection
st.markdown('<div class="sec">🔮 Projected Risk — Next 24 Hours</div>', unsafe_allow_html=True)
fig = go.Figure(go.Scatter(x=list(range(1, len(proj) + 1)), y=proj, mode="lines+markers",
                           line=dict(color="#3b82f6", width=2), marker=dict(size=5)))
for y, name, c in [(25, "Moderate", "#facc15"), (50, "High", "#f59e0b"), (75, "Critical", "#ef4444")]:
    fig.add_hline(y=y, line_dash="dash", line_color=c, annotation_text=name,
                  annotation_position="top right", annotation_font_color="#e2e8f0")
fig.update_layout(height=360, margin=dict(l=10, r=10, t=10, b=10), yaxis=dict(range=[0, 100], title="Flash Flood Risk Index"),
                  xaxis=dict(title="Hours ahead"), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                  font={"color": "#cbd5e1"})
fig.update_xaxes(gridcolor="rgba(255,255,255,.06)")
fig.update_yaxes(gridcolor="rgba(255,255,255,.06)")
show_chart(fig)

st.markdown('<div class="foot">Prototype for research purposes. Weather data: Open-Meteo API. '
            'Chaos model: hybrid weather-driven Lorenz system. Not for operational emergency use.</div>',
            unsafe_allow_html=True)
