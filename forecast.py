"""
forecast.py — прогноз рассеивания загрязнения на N часов вперёд.

Алгоритм:
  1. Берём текущие частицы и данные ветра
  2. Прогоняем симуляцию вперёд на FORECAST_STEPS шагов
  3. На каждом шаге сохраняем snapshot heatmap + avg AQI
  4. Возвращаем список кадров для JS-анимации в браузере
"""
import numpy as np
import config
from physics import wind_displacement, step_particles, emit_particles, trim_particles
from aqi import pm25_to_aqi


def run_forecast(particles: list, df, wind: dict) -> list[dict]:
    
    from copy import deepcopy

    d_lat, d_lon = wind_displacement(
        wind["wind_speed"], wind["wind_deg"], config.DT
    )

    # Стартуем с текущих частиц
    sim_particles = deepcopy(particles)
    frames = []

    for step in range(config.FORECAST_STEPS + 1):
        # snapshot текущего состояния
        heat = [[p["lat"], p["lon"], p["value"]] for p in sim_particles]
        avg_val = np.mean([p["value"] for p in sim_particles]) if sim_particles else 0
        avg_aqi, label, color = pm25_to_aqi(avg_val) # avg_val here is already AQI-based from physics.py

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

        # --- симулируем один шаг вперёд ---
        # Use refined physics for better accuracy in forecast
        sim_particles = step_particles(sim_particles, d_lat, d_lon, step_time=step)
        sim_particles += emit_particles(df)
        sim_particles = trim_particles(sim_particles)

    return frames