"""
physics.py — физика рассеивания загрязнения по ветру
"""

import numpy as np
import config


def wind_displacement(speed_ms: float, direction_deg: float, dt_sec: float) -> tuple:
    """
    Метеорологическое направление: 270° = ветер С запада → частицы летят НА восток.
    Возвращает (d_lat, d_lon) в градусах.
    """
    dist_m   = speed_ms * dt_sec
    move_rad = np.radians(direction_deg + 180.0)   # куда летят частицы
    d_lat = dist_m * np.cos(move_rad) / 111_000
    d_lon = dist_m * np.sin(move_rad) / (111_000 * np.cos(np.radians(config.LAT_CENTER)))
    return float(d_lat), float(d_lon)


def step_particles(particles: list, d_lat: float, d_lon: float) -> list:
    """
    Двигает и затухает все существующие частицы на один шаг.
    """
    new = []
    for p in particles:
        new_val = p["value"] * config.DECAY
        if new_val < 0.5:
            continue
        new.append({
            "lat":   p["lat"]   + d_lat + np.random.uniform(-config.DIFFUSION, config.DIFFUSION),
            "lon":   p["lon"]   + d_lon + np.random.uniform(-config.DIFFUSION, config.DIFFUSION),
            "value": new_val,
        })
    return new


def emit_particles(df) -> list:
    """
    Добавляет новые частицы из каждой станции.
    Значение частицы = AQI (0–500).
    """
    from aqi import pm25_to_aqi
    new = []
    for _, row in df.iterrows():
        aqi, _, _ = pm25_to_aqi(row["pm25"])
        new.append({
            "lat":   row["lat"],
            "lon":   row["lon"],
            "value": float(aqi),
        })
    return new


def trim_particles(particles: list) -> list:
    """Оставляет только MAX_PARTICLES самых сильных частиц."""
    if len(particles) > config.MAX_PARTICLES:
        particles = sorted(particles, key=lambda p: -p["value"])[:config.MAX_PARTICLES]
    return particles
