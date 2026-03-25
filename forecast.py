"""
forecast.py - Pollution dispersion forecast for N hours ahead.

Algorithm:
  1. Take current particles and wind data
  2. Run simulation forward for FORECAST_STEPS steps
  3. At each step, save snapshot heatmap + avg AQI
  4. Return list of frames for JS animation in browser
"""
import numpy as np
import config
from physics import wind_displacement, step_particles, emit_particles, trim_particles
from aqi import pm25_to_aqi, get_aqi_category


def run_forecast(particles: list, df, wind: dict) -> list[dict]:
    
    from copy import deepcopy

    d_lat, d_lon = wind_displacement(
        wind["wind_speed"], wind["wind_deg"], config.DT
    )

    # Start with current particles
    sim_particles = deepcopy(particles)
    frames = []

    for step in range(config.FORECAST_STEPS + 1):
        # Snapshot of current state
        heat = [[p["lat"], p["lon"], p["value"]] for p in sim_particles]
        
        # avg_val is already AQI-based from physics.py
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

        if step == config.FORECAST_STEPS:
            break

        # --- Simulate one step forward ---
        # Use refined physics for better accuracy in forecast
        sim_particles = step_particles(sim_particles, d_lat, d_lon)
        sim_particles += emit_particles(df)
        sim_particles = trim_particles(sim_particles)

    return frames