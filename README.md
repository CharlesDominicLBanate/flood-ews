# Flash Flood Risk Index (FFRI)

Experimental dashboard that estimates flash flood risk for Philippine cities using a
Lorenz-system chaos model driven by live weather data (Open-Meteo, no API key needed).

## Files
- `app.py` – Streamlit dashboard
- `chaos_model.py` – Lorenz simulation, Lyapunov estimate, FFRI computation, risk projection
- `data_fetcher.py` – Open-Meteo weather/elevation fetcher
- `gis_utils.py` – Folium hazard map builder
- `config.py` – constants, risk levels, locations

## Run
```bash
pip install -r requirements.txt
streamlit run app.py
```

## How it works
Weather (rain intensity, 24h accumulation, humidity, soil moisture) maps to Lorenz
parameters (σ, ρ, β). Two nearly identical trajectories are simulated; how fast they
diverge (Lyapunov estimate) gives a chaos signal. This is combined with rainfall,
soil saturation and terrain slope, then passed through a sigmoid to produce a 0–100 index.

> Educational only. Not an official warning system. Follow PAGASA advisories.
