"""
district_ranking.py — District ranking by AQI for the last 24 hours
"""
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from database import DB_PATH

DISTRICT_STATIONS = {
    "Arabkir":          ["Arabkir", "Urartu", "Aytsemnik"],
    "Kentron":          ["Kentron", "Yerevan", "Isakov", "Dro"],
    "Shengavit":        ["Shengavit", "Nzhdeh", "Arshakunyats"],
    "Davtashen":        ["Davtashen"],
    "Malatia-Sebastia": ["Malatia", "Sebastia"],
    "Nor Nork":         ["Nor Nork", "Ulnetsi"],
    "Erebuni":          ["Erebuni", "Artashat"],
    "Kanaker-Zeytun":   ["Kanaker", "Zeytun"],
    "Avan":             ["Avan"],
    "Ajapnyak":         ["Achapnyak"],
    "Nork-Marash":      ["Nork", "Marashen"],
    "Nubarashen":       ["Nubarashen"],
}


def get_district_ranking() -> list[dict]:
    """District ranking by average PM2.5 for the last 24 hours."""
    from database import init_db
    init_db()
    since = (datetime.now() - timedelta(hours=24)).isoformat()

    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute("""
            SELECT station, AVG(pm25) as avg_pm25
            FROM measurements
            WHERE timestamp > ? AND pm25 > 0 AND pm25 < 500
            GROUP BY station
        """, (since,)).fetchall()

    # station_name -> avg_pm25
    station_avgs = {row[0]: row[1] for row in rows}

    ranking = []
    for district, keywords in DISTRICT_STATIONS.items():
        matched = []
        for station_name, avg in station_avgs.items():
            if any(kw.lower() in station_name.lower() for kw in keywords):
                matched.append(avg)

        if matched:
            avg_pm25 = round(sum(matched) / len(matched), 1)
        else:
            continue  # no data — skip

        # AQI from PM2.5
        aqi, label, color = pm25_to_aqi(avg_pm25)
        ranking.append({
            "district": district,
            "pm25":     avg_pm25,
            "aqi":      aqi,
            "label":    label,
            "color":    color,
        })

    # Sort from cleanest to dirtiest
    ranking.sort(key=lambda x: x["pm25"])
    return ranking


def pm25_to_aqi(pm25: float):
    from aqi import pm25_to_aqi as _fn
    return _fn(pm25)