"""
anomaly.py — PM2.5 anomaly detector
If PM2.5 sharply increases — find probable source by wind direction
"""
import sqlite3
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from database import DB_PATH


def get_recent_avg(minutes: int = 30) -> float:
    """Average PM2.5 for the last N minutes."""
    from database import init_db
    init_db()
    since = (datetime.now() - timedelta(minutes=minutes)).isoformat()
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute("""
            SELECT AVG(pm25) FROM measurements
            WHERE timestamp > ? AND pm25 > 0 AND pm25 < 500
        """, (since,)).fetchone()
    return float(row[0]) if row[0] else 0.0


def get_baseline_avg(hours: int = 24) -> float:
    """Baseline average PM2.5 for the last N hours."""
    from database import init_db
    init_db()
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
    """Wind direction → probable pollution source."""
    dirs = [
        (0,   "North"),
        (45,  "Northeast"),
        (90,  "East"),
        (135, "Southeast"),
        (180, "South"),
        (225, "Southwest"),
        (270, "West"),
        (315, "Northwest"),
        (360, "North"),
    ]
    closest = min(dirs, key=lambda d: abs(d[0] - wind_deg))
    return closest[1]


def detect_anomalies(df, wind: dict) -> list[dict]:
    """
    Returns list of anomalies if PM2.5 sharply increased.
    """
    anomalies = []

    recent   = get_recent_avg(30)
    baseline = get_baseline_avg(24)

    if baseline < 1:
        return []  # not enough data

    ratio = recent / baseline if baseline > 0 else 1

    # Anomaly if increase > 50%
    if ratio > 1.5:
        wind_deg   = wind.get("wind_deg", 0)
        wind_speed = wind.get("wind_speed", 0)
        source_dir = find_source_direction(wind_deg)

        severity = "high" if ratio > 2.0 else "medium"
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
                f"PM2.5 increased {ratio:.1f}x. "
                f"Wind from {source_dir} ({wind_speed:.1f} m/s) — "
                f"probable source is {source_dir} of the city."
            ),
        })

    # Check individual stations
    for _, row in df.iterrows():
        if row["pm25"] > baseline * 2.5 and row["pm25"] > 50:
            anomalies.append({
                "type":     "station_spike",
                "severity": "local",
                "color":    "#ab47bc",
                "station":  row["name"],
                "pm25":     round(row["pm25"], 1),
                "baseline": round(baseline, 1),
                "message":  f"Station {row['name'][:30]}: PM2.5={row['pm25']:.1f} (baseline ~{baseline:.1f})",
            })

    return anomalies