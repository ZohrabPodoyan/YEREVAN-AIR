"""
physics.py — физика рассеивания загрязнения по ветру
С добавлением:
  • Шум Перлина для турбулентности (кинематографичный дым)
  • Горный рельеф: замедление и застаивание в низинах
"""

import time

import numpy as np
import config

# Пытаемся импортировать шум Перлина
try:
    from opensimplex import OpenSimplex
    _perlin = OpenSimplex(seed=42)
    _has_perlin = True
except ImportError:
    _has_perlin = False
    print("⚠ opensimplex не установлен (pip install opensimplex) — турбулентность отключена")


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


def get_terrain_factor(lat: float, lon: float) -> float:
    """
    Возвращает коэффициент застаивания загрязнения:
    • Центр Еревана (Кентрон, Шенгавит) — низины → фактор 1.2 (живут дольше)
    • Северо-восточные районы (Аван, Нор-Норк) — выше → фактор 0.7 (быстрее рассеиваются)
    • Западные районы — среднее → фактор 1.0
    """
    # Упрощённая модель: расстояние от центра + направление
    # Ереван: центр ~40.179°N, 44.513°E
    d_lat = abs(lat - config.LAT_CENTER)
    d_lon = abs(lon - config.LON_CENTER)
    
    # Южные и центральные районы — низины
    if lat < config.LAT_CENTER + 0.02:
        return 1.2
    # Северные районы — выше
    elif lat > config.LAT_CENTER + 0.04:
        return 0.7
    else:
        return 1.0


def get_turbulence(lat: float, lon: float, t: float) -> tuple:
    """
    Возвращает (d_lat_turb, d_lon_turb) — турбулентное смещение на основе шума Перлина.
    t — время (можно использовать шаг симуляции или random seed).
    """
    if not _has_perlin:
        # fallback: случайный разброс
        return (
            np.random.uniform(-config.DIFFUSION, config.DIFFUSION),
            np.random.uniform(-config.DIFFUSION, config.DIFFUSION)
        )
    
    # Используем opensimplex для плавного турбулентного поля
    scale = 0.05  # частота шума
    dx = _perlin.noise2(lat * scale + t * 0.1, lon * scale) * config.DIFFUSION * 2
    dy = _perlin.noise2(lat * scale + t * 0.1 + 100, lon * scale) * config.DIFFUSION * 2
    return float(dx), float(dy)


def step_particles(particles: list, d_lat: float, d_lon: float, step_time: float = None) -> list:
    """
    Двигает и затухает все существующие частицы на один шаг.
    step_time — для турбулентности; если не передан, используем текущее время.
    """
    if step_time is None:
        step_time = time.time()
    new = []
    for p in particles:
        # Турбулентность
        turb_lat, turb_lon = get_turbulence(p["lat"], p["lon"], step_time)
        
        # Горный фактор влияет на затухание
        terrain_factor = get_terrain_factor(p["lat"], p["lon"])
        decay = config.DECAY ** terrain_factor  # в низинах затухает медленнее
        
        new_val = p["value"] * decay
        if new_val < 0.5:
            continue
        
        new.append({
            "lat":   p["lat"]   + d_lat + turb_lat,
            "lon":   p["lon"]   + d_lon + turb_lon,
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