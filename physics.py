"""
physics.py - Pollution dispersion physics by wind
With additions:
  - Perlin noise for turbulence (cinematic smoke effect)
  - Mountain terrain: slowdown and stagnation in lowlands
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
    
    # 111,320 meters is more precise for 1 degree of latitude
    d_lat = dist_m * np.cos(move_rad) / 111320
    d_lon = dist_m * np.sin(move_rad) / (111320 * np.cos(np.radians(config.LAT_CENTER)))
    return float(d_lat), float(d_lon)


def get_terrain_factor(lat: float, lon: float) -> float:
    """
    Returns pollution stagnation factor:
    - Yerevan center (Kentron, Shengavit) - lowlands -> factor 1.2 (live longer)
    - Northeastern districts (Avan, Nor-Nork) - higher -> factor 0.7 (disperse faster)
    """
    # Stagnation Thresholds: 
    # Lower latitude = lower elevation in Yerevan's geography.
    
    # Southern and central districts - lowlands
    if lat < config.LAT_CENTER + 0.02:
        return 1.2
    # Northern districts - higher
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
    """ 
    t = step_time if step_time is not None else time.time()
    new = []
    
    # Pre-calculate base decay to save CPU cycles in the loop
    base_decay = config.DECAY

    for p in particles:
        turb_lat, turb_lon = get_turbulence(p["lat"], p["lon"], t)

        # Slower decay in lowlands: if factor > 1, exponent < 1,
        # making the result closer to 1.0 (slower decay)
        actual_decay = base_decay ** (1.0 / get_terrain_factor(p["lat"], p["lon"]))

        new_val = p["value"] * actual_decay
        
        # Optimization: prune invisible particles early
        if new_val < 0.5:
            continue

        new.append({
            "lat":   p["lat"] + d_lat + turb_lat,
            "lon":   p["lon"] + d_lon + turb_lon,
            "value": new_val,
        })
    return new


def emit_particles(df) -> list:
    """
    Adds new particles from each station.
    Particle value = AQI (0-500).
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