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
    dist_m = speed_ms * dt_sec
    
    # 1. Flip the wind: From NE (60) becomes To SW (240)
    # 2. Ensure it stays within 0-360
    target_dir = (direction_deg + 180.0) % 360
    
    # 3. Convert to Radians
    move_rad = np.radians(target_dir)
    
    # 4. Calculation (Assuming 0 is North and CW)
    # North/South displacement
    d_lat = dist_m * np.cos(move_rad) / 111320
    
    # East/West displacement (with longitude correction)
    cos_lat = np.cos(np.radians(config.LAT_CENTER))
    d_lon = dist_m * np.sin(move_rad) / (111320 * cos_lat)
    
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


def emit_particles(df, pm25_rel_jitter: float = 0.0, target_mean_pm25: float | None = None) -> list:
    """
    Adds new particles from each station.
    Particle value = AQI (0-500).
    target_mean_pm25: if set, scale station PM2.5 so mean matches (forecast vs LSTM).
    pm25_rel_jitter: if > 0 and no target, scale each PM2.5 by U(1-j, 1+j).
    """
    from aqi import pm25_to_aqi
    new = []
    mean_pm = float(df["pm25"].mean()) if len(df) else 0.0
    for _, row in df.iterrows():
        pm = float(row["pm25"])
        if target_mean_pm25 is not None and mean_pm > 1e-6:
            pm *= target_mean_pm25 / mean_pm
        elif pm25_rel_jitter > 0:
            pm *= float(np.random.uniform(1.0 - pm25_rel_jitter, 1.0 + pm25_rel_jitter))
            pm = max(0.0, pm)
        aqi, _, _ = pm25_to_aqi(pm)
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