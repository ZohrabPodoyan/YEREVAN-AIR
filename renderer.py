"""
renderer.py - Jinja2 template renderer
"""

import html
import json
from datetime import datetime
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

from aqi import pm25_to_aqi, beaufort_scale
import config

TEMPLATE_DIR = Path(__file__).parent / "templates"

env = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=True,
)


def _prepare_stations(df):
    """Prepare station data for the template."""
    sources = []
    for _, row in df.iterrows():
        aqi, label, color = pm25_to_aqi(row["pm25"])
        sources.append({
            "name":  row["name"],
            "lat":   row["lat"],
            "lon":   row["lon"],
            "aqi":   aqi,
            "label": label,
            "color": color,
            "pm25":  f"{row['pm25']:.1f}",
            "pm10":  f"{row['pm10']:.1f}",
            "no2":   f"{row['no2']:.1f}",
            "o3":    f"{row['o3']:.1f}",
        })
    return sources


def _build_station_cards_html(sources: list) -> str:
    if not sources:
        return '<div class="dist-card" role="status">No station data</div>'
    parts = []
    for s in sources:
        name = html.escape(str(s["name"])[:48])
        col = html.escape(str(s["color"]))
        parts.append(
            f'<div class="dist-card" role="article">'
            f'<div class="dist-dot" style="background-color:{col}"></div>'
            f'<div class="dist-name">{name}</div>'
            f'<div class="dist-aqi" style="color:{col}">{int(s["aqi"])}</div>'
            f'</div>'
        )
    return "\n".join(parts)


def _build_pollutant_bars_html(df) -> str:
    """Average pollutant mini-bars (μg/m³ scale heuristics for bar width)."""
    if df is None or len(df) == 0:
        return '<div class="mini-bar-row"><span class="mini-bar-label">—</span></div>'
    avg = df[["pm25", "pm10", "no2", "o3"]].mean()
    scales = {"pm25": 200.0, "pm10": 400.0, "no2": 200.0, "o3": 200.0}
    labels = {"pm25": "PM2.5", "pm10": "PM10", "no2": "NO₂", "o3": "O₃"}
    parts = []
    for key in ["pm25", "pm10", "no2", "o3"]:
        val = float(avg.get(key, 0) or 0)
        pct = min(100.0, 100.0 * val / max(scales[key], 1e-6))
        parts.append(
            f'<div class="mini-bar-row">'
            f'<span class="mini-bar-label">{labels[key]}</span>'
            f'<div class="mini-bar-track"><div class="mini-bar-fill" '
            f'style="width:{pct:.1f}%;background:var(--theme-primary)"></div></div>'
            f'<span class="mini-bar-val">{val:.1f}</span>'
            f'</div>'
        )
    return "".join(parts)


def _build_ticker_html(sources: list, alerts: list) -> str:
    items = []
    for a in (alerts or [])[:6]:
        msg = html.escape(str(a.get("message", a.get("name", "Alert")))[:100])
        items.append(
            f'<span class="ticker-item">'
            f'<span class="ticker-dot" style="background:var(--error)"></span> {msg}'
            f'</span>'
        )
    for s in (sources or [])[:14]:
        nm = html.escape(str(s["name"])[:36])
        col = html.escape(str(s["color"]))
        items.append(
            f'<span class="ticker-item">'
            f'<span class="ticker-dot" style="background:{col}"></span> '
            f'{nm} · AQI {int(s["aqi"])}'
            f'</span>'
        )
    if not items:
        items.append(
            '<span class="ticker-item">'
            '<span class="ticker-dot" style="background:var(--theme-primary)"></span> '
            'Yerevan Air — live monitoring'
            '</span>'
        )
    return "".join(items)


def render(particles, df, wind, alerts=None, forecast_frames=None,
           prediction=None, vs_reality=None, correlation=None,
           ranking=None, weather_forecast=None, anomalies=None) -> str:
    avg_pm25 = df["pm25"].mean()
    avg_pm10 = df["pm10"].mean()
    avg_aqi, avg_label, avg_color = pm25_to_aqi(avg_pm25)
    gauge_pct = min(99, avg_aqi / 500 * 100)

    heat_data = [[p["lat"], p["lon"], p["value"]] for p in particles]
    history_data = []
    alerts = alerts or []
    forecast_frames = forecast_frames or []
    prediction = prediction or []
    vs_reality = vs_reality or []

    forecast_js = [
        {
            "step":    f["step"],
            "minutes": f["minutes"],
            "hours":   f.get("hours", 0),
            "avg_aqi": f["avg_aqi"],
            "label":   f["label"],
            "color":   f["color"],
            "heat":    f["heat"],
        }
        for f in forecast_frames
    ]

    stations = _prepare_stations(df)
    station_cards = _build_station_cards_html(stations)
    pollutant_bars = _build_pollutant_bars_html(df)
    ticker_items = _build_ticker_html(stations, alerts)

    template = env.get_template("base.html")
    forecast_horizon_h = round(
        config.FORECAST_STEPS * (config.DT / 3600.0), 1
    )

    return template.render(
        forecast_horizon_h = forecast_horizon_h,
        timestamp        = datetime.now().strftime("%H:%M:%S  %d.%m.%Y"),
        particle_count   = len(particles),
        station_count    = len(df),
        wind_speed       = f"{wind['wind_speed']:.1f}",
        wind_speed_raw   = round(wind["wind_speed"], 2),
        wind_deg         = f"{wind['wind_deg']:.0f}",
        wind_deg_raw     = round(wind["wind_deg"], 1),
        beaufort         = beaufort_scale(wind["wind_speed"]),
        avg_aqi          = avg_aqi,
        avg_label        = avg_label,
        aqi_color        = avg_color,
        avg_pm25         = f"{avg_pm25:.1f}",
        avg_pm10         = f"{avg_pm10:.1f}",
        avg_temp         = f"{wind['temp']:.1f}",
        avg_hum          = f"{wind['humidity']:.0f}",
        gauge_pct        = f"{gauge_pct:.1f}",
        lat_center       = config.LAT_CENTER,
        lon_center       = config.LON_CENTER,
        station_cards    = station_cards,
        pollutant_bars   = pollutant_bars,
        ticker_items     = ticker_items,
        heat_json        = json.dumps(heat_data),
        sources_json     = json.dumps(stations),
        history_json     = json.dumps(history_data),
        alerts_json      = json.dumps(alerts),
        forecast_json    = json.dumps(forecast_js),
        prediction_json  = json.dumps(prediction),
        vs_reality_json   = json.dumps(vs_reality),
        correlation_json  = json.dumps(correlation or {}),
        ranking_json      = json.dumps(ranking or []),
        weather_forecast_json = json.dumps(weather_forecast or []),
        anomalies_json        = json.dumps(anomalies or []),
    )
