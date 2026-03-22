"""
anomaly.py — детектор аномалий PM2.5
Если PM2.5 резко вырос — находим вероятный источник по ветру
"""
import sqlite3
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta

DB_PATH = Path(__file__).parent / "air_data.db"


def get_recent_avg(minutes: int = 30) -> float:
    """Средний PM2.5 за последние N минут."""
    since = (datetime.now() - timedelta(minutes=minutes)).isoformat()
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute("""
            SELECT AVG(pm25) FROM measurements
            WHERE timestamp > ? AND pm25 > 0 AND pm25 < 500
        """, (since,)).fetchone()
    return float(row[0]) if row[0] else 0.0


def get_baseline_avg(hours: int = 24) -> float:
    """Базовый средний PM2.5 за последние N часов."""
    since = (datetime.now() - timedelta(hours=hours)).isoformat()
    until = (datetime.now() - timedelta(minutes=30)).isoformat()
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute("""
            SELECT AVG(pm25) FROM measurements
            WHERE timestamp > ? AND timestamp < ?
            AND pm25 > 0 AND pm25 < 500
        """, (since, until)).fetchone()
    return float(row[0]) if row[0] else 0.0


def find_source_direction(wind_deg: float) -> str:
    """Откуда дует ветер → вероятный источник загрязнения."""
    dirs = [
        (0,   "севера"),
        (45,  "северо-востока"),
        (90,  "востока"),
        (135, "юго-востока"),
        (180, "юга"),
        (225, "юго-запада"),
        (270, "запада"),
        (315, "северо-запада"),
        (360, "севера"),
    ]
    closest = min(dirs, key=lambda d: abs(d[0] - wind_deg))
    return closest[1]


def detect_anomalies(df, wind: dict) -> list[dict]:
    """
    Возвращает список аномалий если PM2.5 резко вырос.
    """
    anomalies = []

    recent   = get_recent_avg(30)
    baseline = get_baseline_avg(24)

    if baseline < 1:
        return []  # мало данных

    ratio = recent / baseline if baseline > 0 else 1

    # Аномалия если рост > 50%
    if ratio > 1.5:
        wind_deg   = wind.get("wind_deg", 0)
        wind_speed = wind.get("wind_speed", 0)
        source_dir = find_source_direction(wind_deg)

        severity = "высокая" if ratio > 2.0 else "средняя"
        color    = "#ef5350" if ratio > 2.0 else "#ffa726"

        anomalies.append({
            "type":       "pm25_spike",
            "severity":   severity,
            "color":      color,
            "recent":     round(recent, 1),
            "baseline":   round(baseline, 1),
            "ratio":      round(ratio, 2),
            "wind_deg":   wind_deg,
            "wind_speed": round(wind_speed, 1),
            "source_dir": source_dir,
            "message":    (
                f"PM2.5 вырос в {ratio:.1f}x раз. "
                f"Ветер с {source_dir} ({wind_speed:.1f} м/с) — "
                f"вероятный источник находится к {source_dir} от города."
            ),
        })

    # Проверка отдельных станций
    for _, row in df.iterrows():
        if row["pm25"] > baseline * 2.5 and row["pm25"] > 50:
            anomalies.append({
                "type":     "station_spike",
                "severity": "локальная",
                "color":    "#ab47bc",
                "station":  row["name"],
                "pm25":     round(row["pm25"], 1),
                "baseline": round(baseline, 1),
                "message":  f"Станция {row['name'][:30]}: PM2.5={row['pm25']:.1f} (норма ~{baseline:.1f})",
            })

    return anomalies