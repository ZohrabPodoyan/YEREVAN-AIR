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
from physics import wind_displacement
from aqi import pm25_to_aqi

# Сколько шагов прогноза (1 шаг = DT сек = 5 мин)
FORECAST_STEPS = 12   # = 1 час вперёд


def run_forecast(particles: list, df, wind: dict) -> list[dict]:
    """
    Возвращает список кадров:
    [
      {
        "step": 0,           # номер шага
        "minutes": 0,        # минут от сейчас
        "avg_aqi": 69,       # средний AQI по всем частицам
        "heat": [[lat,lon,val], ...]  # heatmap данные
      },
      ...
    ]
    """
    from copy import deepcopy

    d_lat, d_lon = wind_displacement(
        wind["wind_speed"], wind["wind_deg"], config.DT
    )

    # Стартуем с текущих частиц
    sim_particles = deepcopy(particles)
    frames = []

    for step in range(FORECAST_STEPS + 1):
        # snapshot текущего состояния
        heat = [[p["lat"], p["lon"], p["value"]] for p in sim_particles]
        avg_aqi = int(np.mean([p["value"] for p in sim_particles])) if sim_particles else 0
        _, label, color = pm25_to_aqi(avg_aqi)

        frames.append({
            "step":    step,
            "minutes": step * (config.DT // 60),
            "avg_aqi": avg_aqi,
            "label":   label,
            "color":   color,
            "heat":    heat,
        })

        if step == FORECAST_STEPS:
            break

        # --- симулируем один шаг вперёд ---
        new_p = []
        for p in sim_particles:
            nv = p["value"] * config.DECAY
            if nv < 0.5:
                continue
            new_p.append({
                "lat":   p["lat"]   + d_lat + np.random.uniform(-config.DIFFUSION, config.DIFFUSION),
                "lon":   p["lon"]   + d_lon + np.random.uniform(-config.DIFFUSION, config.DIFFUSION),
                "value": nv,
            })

        # добавляем новые эмиссии из источников
        for _, row in df.iterrows():
            aqi_val, _, _ = pm25_to_aqi(row["pm25"])
            new_p.append({"lat": row["lat"], "lon": row["lon"], "value": float(aqi_val)})

        # лимит
        if len(new_p) > config.MAX_PARTICLES:
            new_p = sorted(new_p, key=lambda x: -x["value"])[:config.MAX_PARTICLES]

        sim_particles = new_p

    return frames