import numpy as np
from scipy.integrate import odeint

from config import SIM_STEPS, SIM_DT, LYAPUNOV_EPSILON, RISK_LEVELS


def _lorenz_deriv(state, t, sigma, rho, beta):
    x, y, z = state
    dx = sigma * (y - x)
    dy = x * (rho - z) - y
    dz = x * y - beta * z
    return [dx, dy, dz]


def _map_weather_to_params(weather: dict, slope_factor: float):
  
    rain = max(weather.get("rain_mm", 0.0), weather.get("precipitation_mm", 0.0))
    accum_24h = weather.get("precip_accum_24h_mm", 0.0)
    humidity = weather.get("humidity_pct", 50.0)
    soil_moisture = weather.get("soil_moisture", 0.2)

    # sigma: energy/moisture transfer term
    sigma = 8.0 + (humidity / 100.0) * 4.0  # roughly 8-12

    # rho: the classic chaos-onset parameter. Lorenz becomes chaotic around
    # rho ~ 24.74 in the classic system. We scale real rainfall intensity so
    # that heavy rain pushes rho well past that chaotic threshold.
    rain_intensity_score = min(rain / 20.0, 1.0)          # normalize: 20mm/hr = saturated
    accumulation_score = min(accum_24h / 100.0, 1.0)      # normalize: 100mm/24h = saturated
    rho = 10.0 + (rain_intensity_score * 0.6 + accumulation_score * 0.4) * 35.0  # ~10-45

    # beta: dissipation. Saturated soil + steep slope = poor dissipation = lower beta
    drainage_capacity = (1.0 - soil_moisture) * (1.0 - slope_factor)
    beta = 1.0 + drainage_capacity * 3.5  # roughly 1.0 (poor drainage) to 4.5 (good drainage)

    return sigma, rho, beta


def run_chaos_simulation(weather: dict, slope_factor: float = 0.6):
   
    sigma, rho, beta = _map_weather_to_params(weather, slope_factor)

    t = np.linspace(0, SIM_STEPS * SIM_DT, SIM_STEPS)

    state0 = np.array([1.0, 1.0, 1.0])
    state0_perturbed = state0 + np.array([LYAPUNOV_EPSILON, 0.0, 0.0])

    traj_a = odeint(_lorenz_deriv, state0, t, args=(sigma, rho, beta))
    traj_b = odeint(_lorenz_deriv, state0_perturbed, t, args=(sigma, rho, beta))

    separation = np.linalg.norm(traj_a - traj_b, axis=1)
    separation = np.clip(separation, 1e-12, None)

    log_sep = np.log(separation / LYAPUNOV_EPSILON)
    half = len(t) // 2
    if t[-1] - t[half] > 0:
        lyap_estimate = (log_sep[-1] - log_sep[half]) / (t[-1] - t[half])
    else:
        lyap_estimate = 0.0
    lyap_estimate = max(lyap_estimate, 0.0)

    accum_24h = weather.get("precip_accum_24h_mm", 0.0)
    soil_moisture = weather.get("soil_moisture", 0.2)

    chaos_signal = np.tanh(lyap_estimate / 3.0)              # instability from chaos model
    rainfall_signal = min(accum_24h / 120.0, 1.0)             # accumulated rainfall
    saturation_signal = min(soil_moisture / 0.5, 1.0)         # soil saturation
    terrain_signal = slope_factor                              # static terrain vulnerability

    composite = (
        0.40 * chaos_signal +
        0.30 * rainfall_signal +
        0.20 * saturation_signal +
        0.10 * terrain_signal
    )

    ffri = 100.0 / (1.0 + np.exp(-8.0 * (composite - 0.5)))

    risk_label, risk_color = classify_risk(ffri)

    return {
        "sigma": sigma,
        "rho": rho,
        "beta": beta,
        "trajectory": traj_a,
        "time": t,
        "lyapunov_estimate": lyap_estimate,
        "chaos_signal": chaos_signal,
        "rainfall_signal": rainfall_signal,
        "saturation_signal": saturation_signal,
        "terrain_signal": terrain_signal,
        "ffri": float(ffri),
        "risk_label": risk_label,
        "risk_color": risk_color,
    }


def classify_risk(ffri: float):
    for low, high, label, color in RISK_LEVELS:
        if low <= ffri < high:
            return label, color
    return "CRITICAL", "#e74c3c"


def project_risk_timeseries(current_ffri: float, hourly_precip: list, soil_moisture: float):
   
    horizon = len(hourly_precip) if hourly_precip else 12
    projected = []
    running_risk = current_ffri
    running_saturation = soil_moisture

    for i in range(horizon):
        rain_i = hourly_precip[i] if i < len(hourly_precip) and hourly_precip[i] is not None else 0.0
        running_saturation = min(running_saturation + rain_i * 0.01, 1.0)
        delta = (rain_i * 2.2) + (running_saturation * 5.0) - 3.0  # decay term
        running_risk = float(np.clip(running_risk + delta, 0, 100))
        projected.append(running_risk)

    return projected
