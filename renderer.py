"""
renderer.py — читает template.html и подставляет данные
"""

import json
import os
from datetime import datetime
from pathlib import Path

from aqi import pm25_to_aqi, beaufort_scale
import config
from history import get_city_history

# Путь к шаблону рядом с этим файлом
TEMPLATE_PATH = Path(__file__).parent / "template.html"


def _station_cards(df) -> str:
    html = ""
    for _, row in df.iterrows():
        aqi, label, color = pm25_to_aqi(row["pm25"])
        name = row["name"]
        short = (name[:24] + "…") if len(name) > 24 else name
        html += (
            f'<div class="dist-card">'
            f'<div class="dist-dot" style="background:{color};box-shadow:0 0 6px {color}"></div>'
            f'<div class="dist-name" title="{name}">{short}</div>'
            f'<div class="dist-aqi" style="color:{color}">{aqi}</div>'
            f'</div>'
        )
    return html


def _pollutant_bars(df) -> str:
    pollutants = [
        ("PM2.5", df["pm25"].mean(), 250,  "#00d4ff"),
        ("PM10 ", df["pm10"].mean(), 430,  "#7ecfff"),
        ("NO₂  ", df["no2"].mean(),  200,  "#ffa726"),
        ("O₃   ", df["o3"].mean(),   240,  "#69f0ae"),
    ]
    html = ""
    for name, val, maxv, color in pollutants:
        # пропускаем если все станции вернули 0
        if val == 0.0:
            continue
        pct = min(100, val / maxv * 100) if maxv else 0
        html += (
            f'<div class="mini-bar-row">'
            f'<div class="mini-bar-label">{name}</div>'
            f'<div class="mini-bar-track">'
            f'<div class="mini-bar-fill" style="width:{pct:.1f}%;background:{color}"></div>'
            f'</div>'
            f'<div class="mini-bar-val">{val:.1f}</div>'
            f'</div>'
        )
    return html

def _ticker_items(df) -> str:
    html = ""
    for _, row in df.iterrows():
        aqi, label, color = pm25_to_aqi(row["pm25"])
        html += (
            f'<div class="ticker-item">'
            f'<div class="ticker-dot" style="background:{color}"></div>'
            f'<span>{row["name"].upper()} &nbsp; '
            f'AQI <b style="color:{color}">{aqi}</b> &nbsp; '
            f'PM2.5 {row["pm25"]:.1f}μg/m³ &nbsp; '
            f'PM10 {row["pm10"]:.1f}μg/m³'
            f'</span></div>'
        )
    return html


def _sources_json(df) -> str:
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
    return json.dumps(sources)


def render(particles, df, wind, alerts=None, forecast_frames=None,
           prediction=None, vs_reality=None) -> str:
    template = TEMPLATE_PATH.read_text(encoding="utf-8")

    avg_pm25 = df["pm25"].mean()
    avg_pm10 = df["pm10"].mean()
    avg_aqi, avg_label, avg_color = pm25_to_aqi(avg_pm25)
    gauge_pct = min(99, avg_aqi / 500 * 100)

    heat_data = [[p["lat"], p["lon"], p["value"]] for p in particles]

    history_data   = get_city_history()
    alerts         = alerts or []
    forecast_frames = forecast_frames or []
    # компактная версия forecast для JS (убираем лишние поля heat из промежуточных)
    forecast_js = [
        {
            "step":    f["step"],
            "minutes": f["minutes"],
            "avg_aqi": f["avg_aqi"],
            "label":   f["label"],
            "color":   f["color"],
            "heat":    f["heat"],
        }
        for f in forecast_frames
    ]

    prediction = prediction or []
    vs_reality = vs_reality or []

    replacements = {
        "{{history_json}}":   json.dumps(history_data),
        "{{alerts_json}}":    json.dumps(alerts),
        "{{forecast_json}}":  json.dumps(forecast_js),
        "{{timestamp}}":      datetime.now().strftime("%H:%M:%S  %d.%m.%Y"),
        "{{particle_count}}": str(len(particles)),
        "{{station_count}}":  str(len(df)),
        "{{wind_speed}}":     f"{wind['wind_speed']:.1f}",
        "{{wind_speed_raw}}": str(round(wind["wind_speed"], 2)),
        "{{wind_deg}}":       f"{wind['wind_deg']:.0f}",
        "{{wind_deg_raw}}":   str(round(wind["wind_deg"], 1)),
        "{{beaufort}}":       str(beaufort_scale(wind["wind_speed"])),
        "{{avg_aqi}}":        str(avg_aqi),
        "{{avg_label}}":      avg_label,
        "{{aqi_color}}":      avg_color,
        "{{avg_pm25}}":       f"{avg_pm25:.1f}",
        "{{avg_pm10}}":       f"{avg_pm10:.1f}",
        "{{avg_temp}}":       f"{wind['temp']:.1f}",
        "{{avg_hum}}":        f"{wind['humidity']:.0f}",
        "{{gauge_pct}}":      f"{gauge_pct:.1f}",
        "{{lat_center}}":     str(config.LAT_CENTER),
        "{{lon_center}}":     str(config.LON_CENTER),
        "{{station_cards}}":  _station_cards(df),
        "{{pollutant_bars}}": _pollutant_bars(df),
        "{{ticker_items}}":   _ticker_items(df),
        "{{heat_json}}":      json.dumps(heat_data),
        "{{sources_json}}":   _sources_json(df),
        "{{prediction_json}}": json.dumps(prediction),
        "{{vs_reality_json}}": json.dumps(vs_reality),
    }

    for placeholder, value in replacements.items():
        template = template.replace(placeholder, value)

    return template
