# 🌊 Flash Flood Early Warning System (EWS) Dashboard

**GIS-Integrated Hybrid Chaos Theory-Based Predictive Modeling of Localized Flash
Flood Risk Using Real-Time Weather and Spatial Data**

A working prototype: ingests live weather data, runs it through a hybrid
chaos-theory model, and visualizes flash flood risk on an interactive
Web-GIS dashboard.

---

## 1. What's inside

| File | Purpose |
|---|---|
| `app.py` | Main Streamlit dashboard (UI/UX, layout, charts, map) |
| `data_fetcher.py` | Real-time weather + spatial (elevation) data ingestion (Open-Meteo API, free/no key) |
| `chaos_model.py` | The hybrid chaos-theory predictive core (weather-driven Lorenz system + Lyapunov-based risk index) |
| `gis_utils.py` | Builds the interactive hazard map (Folium) |
| `config.py` | Monitoring sites, thresholds, and tunable settings |
| `requirements.txt` | Python dependencies |

## 2. How the model works (for your paper/defense)

1. **Real-time ingestion**: current rainfall, humidity, temperature, and
   soil moisture are pulled live from the Open-Meteo API for each
   monitored coordinate (spatial data).
2. **Hybridization**: these weather values are mapped onto the three
   control parameters of a Lorenz chaotic system — σ (moisture/energy
   transfer), ρ (rainfall-driven chaos-onset parameter), β (drainage/
   dissipation, informed by soil saturation + terrain slope).
3. **Chaos simulation**: the system is integrated forward in time
   alongside an infinitesimally perturbed twin trajectory. How fast the
   two diverge estimates a local **Lyapunov exponent** — a measure of how
   unstable/unpredictable the local hydrological system currently is.
4. **Flash Flood Risk Index (FFRI)**: the Lyapunov-based instability
   signal is combined with rainfall accumulation, soil saturation, and
   terrain vulnerability into one 0–100 index via a logistic function.
5. **Visualization**: the FFRI, its trend, and the underlying chaos
   attractor are rendered live on the dashboard and mapped geographically.

> This is a research-prototype-level hybridization intended to be
> explainable and defensible, not a hydrologically-validated production
> model. You can and should tune the weight coefficients, thresholds, and
> parameter mappings in `chaos_model.py` and `config.py` to match your
> study area calibration data.

## 3. Setup

```bash
pip install -r requirements.txt
```

## 4. Run

```bash
streamlit run app.py
```

This opens the dashboard in your browser (usually `http://localhost:8501`).

## 5. Using the dashboard

- **Sidebar → Monitoring Site**: switch between predefined flood-prone
  locations (edit `LOCATIONS` in `config.py` to add your own study area
  coordinates).
- **Live auto-refresh**: toggle on to simulate continuous streaming —
  the dashboard re-pulls weather and re-runs the chaos model on an
  interval you control.
- **Offline demo mode**: turn this on if you're presenting without
  internet (e.g., during your thesis defense) — it generates realistic
  simulated weather instead of calling the live API, so the dashboard
  still behaves like it's "live."
- **Web-GIS map**: shows every monitored site at once, color-coded and
  sized by current risk level. Click a marker for details.
- **Chaos attractor plot**: 3D visualization of the current Lorenz
  trajectory — a visual, defensible link back to "chaos theory" in your
  title.
- **Risk gauge + contributing signals**: breaks down exactly how much
  each factor (chaos instability, rainfall, soil saturation, terrain)
  contributed to the current index.
- **24-hour forecast timeline**: projects how risk is expected to evolve
  using forecast rainfall.

## 6. Extending this for your full study

- Swap `LOCATIONS` for your actual study-area barangays/watersheds with
  real slope/terrain data from a DEM (e.g., SRTM, or PhilGIS shapefiles)
  instead of the hardcoded `slope_factor`.
- Add historical flood event data to calibrate/validate the FFRI
  thresholds in `config.py` (currently illustrative: 0–25 Low, 25–50
  Moderate, 50–75 High, 75–100 Critical).
- Add SMS/email alerting when a site crosses "HIGH"/"CRITICAL" (e.g. via
  Twilio or a Facebook/Telegram bot) to complete the "early warning"
  aspect operationally.
- If you have access to river-gauge or IoT sensor data, replace/augment
  `data_fetcher.py`'s Open-Meteo calls with your sensor feed.
