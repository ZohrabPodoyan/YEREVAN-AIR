"""
forecast.py - Pollution dispersion forecast for N hours ahead.

Algorithm:
  1. Take current particles and wind data
  2. Run simulation forward for FORECAST_STEPS steps
  3. At each step, save snapshot heatmap + avg AQI
  4. Return list of frames for JS animation in browser

Each hour uses:
  - Wind from OpenWeatherMap 3-hourly forecast, interpolated to that hour (not random).
  - City-mean PM2.5 from the LSTM horizons (interpolated), scaling station emissions to match
    the same model as the PREDICTION tab — so the trend can rise or fall with the forecast.
"""
import numpy as np
import config
from physics import wind_displacement, step_particles, emit_particles, trim_particles
from aqi import get_aqi_category, pm25_to_aqi
from predictor import pm25_at_hour


def run_forecast(
    particles: list,
    df,
    wind: dict,
    prediction: list | None = None,
    hourly_wind: list | None = None,
) -> list:

    from copy import deepcopy

    nh = config.FORECAST_STEPS
    if hourly_wind is None or len(hourly_wind) < nh + 1:
        w = dict(wind)
        hourly_wind = [
            {"wind_speed": w["wind_speed"], "wind_deg": w["wind_deg"]}
            for _ in range(nh + 1)
        ]

    # Start with current map particles; if none (decayed / cold start), seed from stations
    # so "NOW" matches live AQI instead of showing 0.
    sim_particles = deepcopy(particles)
    if not sim_particles and df is not None and len(df) > 0:
        sim_particles = emit_particles(df)

    frames = []

    for step in range(nh + 1):
        # Snapshot of current state
        heat = [[p["lat"], p["lon"], p["value"]] for p in sim_particles]

        # Step 0 "NOW": same city metric as LIVE tab — AQI(mean PM2.5), not mean(per-station AQI).
        # (EPA AQI is piecewise-linear in PM2.5, so those two averages differ.)
        if step == 0 and df is not None and len(df) > 0:
            avg_aqi, label, color = pm25_to_aqi(float(df["pm25"].mean()))
        else:
            avg_aqi = int(round(np.mean([p["value"] for p in sim_particles]))) if sim_particles else 0
            label, color = get_aqi_category(avg_aqi)

        frames.append({
            "step":    step,
            "minutes": step * (config.DT // 60),
            "hours":   round(step * (config.DT / 3600), 1),
            "avg_aqi": avg_aqi,
            "label":   label,
            "color":   color,
            "heat":    heat,
        })

        if step == nh:
            break

        # Wind for the upcoming hour: OWM-interpolated series index step+1
        wstep = hourly_wind[step + 1]
        d_lat, d_lon = wind_displacement(
            float(wstep["wind_speed"]),
            float(wstep["wind_deg"]),
            config.DT,
        )

        sim_particles = step_particles(sim_particles, d_lat, d_lon)

        # Emissions scaled to LSTM city-mean PM2.5 at this horizon (or flat if no model)
        if df is not None and len(df) > 0:
            if prediction:
                target_pm = pm25_at_hour(prediction, float(step + 1))
            else:
                target_pm = float(df["pm25"].mean())
            sim_particles += emit_particles(df, target_mean_pm25=target_pm)
        sim_particles = trim_particles(sim_particles)

    return frames
