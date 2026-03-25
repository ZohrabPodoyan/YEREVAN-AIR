"""
physics.py — Pollution dispersion physics by wind
With additions:
  • Perlin noise for turbulence (cinematic smoke effect)
  • Mountain terrain: slowdown and stagnation in lowlands
"""

import time

import numpy as np
import config

# Try to import Perlin noise
try:
    from opensimplex import OpenSimplex
    _perlin = OpenSimplex(seed=42)
    _has_perlin = True
except ImportError:
    _has_perlin = False
    print("⚠ opensimplex not installed (pip install opensimplex) — turbulence disabled")


def wind_displacement(speed_ms: float, direction_deg: float, dt_sec: float) -> tuple:
    """
    Meteorological direction: 270° = wind FROM west → particles fly TO east.
    Returns (d_lat, d_lon) in degrees.
    """
    dist_m   = speed_ms * dt_sec
    move_rad = np.radians(direction_deg + 180.0)   # where particles fly
    d_lat = dist_m * np.cos(move_rad) / 111_000
    d_lon = dist_m * np.sin(move_rad) / (111_000 * np.cos(np.radians(config.LAT_CENTER)))
    return float(d_lat), float(d_lon)


def get_terrain_factor(lat: float, lon: float) -> float:
    """
    Returns pollution stagnation factor:
    • Yerevan center (Kentron, Shengavit) — lowlands → factor 1.2 (live longer)
    • Northeastern districts (Avan, Nor-Nork) — higher → factor 0.7 (disperse faster)
    • Western districts — average → factor 1.0
    """
    # Simplified model: distance from center + direction
    # Yerevan: center ~40.179°N, 44.513°E
    d_lat = abs(lat - config.LAT_CENTER)
    d_lon = abs(lon - config.LON_CENTER)

    # Southern and central districts — lowlands
    if lat < config.LAT_CENTER + 0.02:
        return 1.2
    # Northern districts — higher
    elif lat > config.LAT_CENTER + 0.04:
        return 0.7
    else:
        return 1.0


def get_turbulence(lat: float, lon: float, t: float) -> tuple:
    """
    Returns (d_lat_turb, d_lon_turb) — turbulent displacement based on Perlin noise.
    t — time (can use simulation step or random seed).
    """
    if not _has_perlin:
        # fallback: random scatter
        return (
            np.random.uniform(-config.DIFFUSION, config.DIFFUSION),
            np.random.uniform(-config.DIFFUSION, config.DIFFUSION)
        )

    # Use opensimplex for smooth turbulent field
    scale = 0.05  # noise frequency
    dx = _perlin.noise2(lat * scale + t * 0.1, lon * scale) * config.DIFFUSION * 2
    dy = _perlin.noise2(lat * scale + t * 0.1 + 100, lon * scale) * config.DIFFUSION * 2
    return float(dx), float(dy)


def step_particles(particles: list, d_lat: float, d_lon: float, step_time: float = None) -> list:
    """
    Moves and decays all existing particles by one step.
    step_time — for turbulence; if not passed, use current time.
    """
    if step_time is None:
        step_time = time.time()
    new = []
    for p in particles:
        # Turbulence
        turb_lat, turb_lon = get_turbulence(p["lat"], p["lon"], step_time)

        # Terrain factor affects decay
        terrain_factor = get_terrain_factor(p["lat"], p["lon"])
        decay = config.DECAY ** terrain_factor  # slower decay in lowlands

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
    Adds new particles from each station.
    Particle value = AQI (0–500).
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
    """Keeps only MAX_PARTICLES strongest particles."""
    if len(particles) > config.MAX_PARTICLES:
        particles = sorted(particles, key=lambda p: -p["value"])[:config.MAX_PARTICLES]
    return particles