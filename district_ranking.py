"""
district_ranking.py — рейтинг районов по AQI за последние 24 часа
"""
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta

DB_PATH = Path(__file__).parent / "air_data.db"

DISTRICT_STATIONS = {
    "Арабкир":          ["Arabkir", "Urartu", "Aytsemnik"],
    "Кентрон":          ["Kentron", "Yerevan", "Isakov", "Dro"],
    "Шенгавит":         ["Shengavit", "Nzhdeh", "Arshakunyats"],
    "Давташен":         ["Davtashen"],
    "Малатия-Себастия": ["Malatia", "Sebastia"],
    "Нор-Норк":         ["Nor Nork", "Ulnetsi"],
    "Эребуни":          ["Erebuni", "Artashat"],
    "Канакер-Зейтун":   ["Kanaker", "Zeytun"],
    "Аван":             ["Avan"],
    "Ачапняк":          ["Achapnyak"],
    "Норк-Мараш":       ["Nork", "Marashen"],
    "Нубарашен":        ["Nubarashen"],
}


def get_district_ranking() -> list[dict]:
    """Рейтинг районов по среднему PM2.5 за последние 24 часа."""
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
            continue  # нет данных — пропускаем

        # AQI из PM2.5
        aqi, label, color = pm25_to_aqi(avg_pm25)
        ranking.append({
            "district": district,
            "pm25":     avg_pm25,
            "aqi":      aqi,
            "label":    label,
            "color":    color,
        })

    # Сортируем от чистого к грязному
    ranking.sort(key=lambda x: x["pm25"])
    return ranking


def pm25_to_aqi(pm25: float):
    from aqi import pm25_to_aqi as _fn
    return _fn(pm25)