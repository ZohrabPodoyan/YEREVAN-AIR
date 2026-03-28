"""
weather_forecast.py - Weather and AQI forecast for 3 days from OWM
"""
import logging
import math
import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from aqi import pm25_to_aqi
import config

logger = logging.getLogger(__name__)


def _session():
    s = requests.Session()
    retries = Retry(total=3, backoff_factor=0.4, status_forcelist=(502, 503, 504))
    s.mount("https://", HTTPAdapter(max_retries=retries))
    s.mount("http://", HTTPAdapter(max_retries=retries))
    return s


def fetch_openwm_forecast(cnt: int = 40) -> dict | None:
    """
    Raw OWM 2.5 /forecast payload (3-hourly steps). cnt max 40 on free tier.
    Returns None on failure.
    """
    try:
        r = _session().get(
            "http://api.openweathermap.org/data/2.5/forecast",
            params={
                "lat":   config.LAT_CENTER,
                "lon":   config.LON_CENTER,
                "appid": config.OWM_KEY,
                "units": "metric",
                "cnt":   min(40, max(8, cnt)),
            },
            timeout=10,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.warning("OWM Forecast fetch error: %s", e)
        return None


def _interp_wind_deg(deg0: float, deg1: float, t: float) -> float:
    """Interpolate wind direction (degrees) linearly on the circle, t in [0, 1]."""
    a0 = math.radians(deg0)
    a1 = math.radians(deg1)
    x = (1.0 - t) * math.cos(a0) + t * math.cos(a1)
    y = (1.0 - t) * math.sin(a0) + t * math.sin(a1)
    return math.degrees(math.atan2(y, x)) % 360.0


def _wind_points_from_owm(data: dict | None, current_wind: dict) -> list[tuple[float, float, float]]:
    """Build sorted (hours_from_now, speed_m_s, deg) points; h=0 is live observation."""
    ws0 = float(current_wind.get("wind_speed", 0.0))
    wd0 = float(current_wind.get("wind_deg", 0.0))
    pts: list[tuple[float, float, float]] = [(0.0, ws0, wd0)]
    if not data or not data.get("list"):
        return pts
    now = time.time()
    for item in data["list"]:
        h = (float(item["dt"]) - now) / 3600.0
        if h < 0.2:
            continue
        ws = float(item.get("wind", {}).get("speed", 0.0))
        wd = float(item.get("wind", {}).get("deg", 0.0))
        pts.append((h, ws, wd))
    pts.sort(key=lambda p: p[0])
    return pts


def _sample_wind_at_hour(pts: list[tuple[float, float, float]], hour: float) -> tuple[float, float]:
    """Interpolate / extrapolate wind at `hour` hours from now."""
    if not pts:
        return 0.0, 0.0
    if hour <= pts[0][0]:
        return pts[0][1], pts[0][2]
    for i in range(len(pts) - 1):
        h0, s0, d0 = pts[i]
        h1, s1, d1 = pts[i + 1]
        if h0 <= hour <= h1:
            if abs(h1 - h0) < 1e-6:
                return s0, d0
            t = (hour - h0) / (h1 - h0)
            ws = s0 + t * (s1 - s0)
            wd = _interp_wind_deg(d0, d1, t)
            return max(0.0, ws), wd
    # Beyond last point: hold last (stable; avoids wild extrapolation)
    return max(0.0, pts[-1][1]), pts[-1][2]


def get_hourly_wind_series(
    n_hours: int,
    current_wind: dict,
    owm_data: dict | None = None,
) -> list[dict]:
    """
    Wind at hour 0, 1, …, n_hours from now.
    Uses OWM 3-hourly grid + interpolation; falls back to current wind if OWM missing.
    """
    data = owm_data if owm_data is not None else fetch_openwm_forecast(40)
    pts = _wind_points_from_owm(data, current_wind)
    out = []
    for h in range(n_hours + 1):
        ws, wd = _sample_wind_at_hour(pts, float(h))
        out.append({"wind_speed": ws, "wind_deg": wd})
    return out


def get_weather_forecast(owm_data: dict | None = None) -> list[dict]:
    """OWM forecast 5 days / 3 hours -> take one per day (noon samples)."""
    try:
        data = owm_data if owm_data is not None else fetch_openwm_forecast(24)
        if not data:
            return []

        days = {}
        for item in data.get("list", []):
            date = item["dt_txt"][:10]
            hour = int(item["dt_txt"][11:13])
            if hour != 12:
                continue

            wind_speed = item.get("wind", {}).get("speed", 0)
            wind_deg   = item.get("wind", {}).get("deg", 0)
            temp       = item.get("main", {}).get("temp", 0)
            humidity   = item.get("main", {}).get("humidity", 0)
            weather    = item.get("weather", [{}])[0]
            icon       = weather.get("main", "Clear")
            desc       = weather.get("description", "")
            clouds     = item.get("clouds", {}).get("all", 0)
            rain       = item.get("rain", {}).get("3h", 0)

            base_pm25 = 20.0
            if rain > 0:
                base_pm25 *= 0.5
            if wind_speed > 5:
                base_pm25 *= 0.7
            if wind_speed < 1:
                base_pm25 *= 1.4
            if humidity > 80:
                base_pm25 *= 1.2
            if clouds < 20:
                base_pm25 *= 0.9

            aqi, label, color = pm25_to_aqi(round(base_pm25, 1))

            days[date] = {
                "date":       date,
                "temp":       round(temp, 1),
                "humidity":   humidity,
                "wind_speed": round(wind_speed, 1),
                "wind_deg":   wind_deg,
                "icon":       icon,
                "desc":       desc,
                "clouds":     clouds,
                "rain":       rain,
                "est_pm25":   round(base_pm25, 1),
                "est_aqi":    aqi,
                "est_label":  label,
                "est_color":  color,
            }

        return list(days.values())[:3]

    except Exception as e:
        logger.warning("OWM Forecast error: %s", e)
        return []
