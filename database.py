"""
database.py — сбор исторических данных в SQLite для обучения модели.

Таблица measurements:
  timestamp, station_name, lat, lon,
  pm25, pm10, no2, o3,
  wind_speed, wind_deg, temp, humidity,
  hour, day_of_week, month
"""

import sqlite3
from datetime import datetime
from pathlib import Path

import os
DB_PATH = Path(os.environ.get("DB_PATH", Path(__file__).parent / "air_data.db"))
DB_PATH=/data/air_data.db


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS measurements (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   TEXT NOT NULL,
            station     TEXT NOT NULL,
            lat         REAL,
            lon         REAL,
            pm25        REAL,
            pm10        REAL,
            no2         REAL,
            o3          REAL,
            wind_speed  REAL,
            wind_deg    REAL,
            temp        REAL,
            humidity    REAL,
            hour        INTEGER,
            day_of_week INTEGER,
            month       INTEGER
        )""")
        conn.commit()


def save_measurements(df, wind: dict):
    """Сохраняет текущие данные всех станций."""
    now = datetime.now()
    rows = []
    for _, row in df.iterrows():
        rows.append((
            now.isoformat(),
            row["name"],
            row["lat"], row["lon"],
            row["pm25"], row["pm10"], row["no2"], row["o3"],
            wind["wind_speed"], wind["wind_deg"],
            wind["temp"], wind["humidity"],
            now.hour, now.weekday(), now.month,
        ))
    with sqlite3.connect(DB_PATH) as conn:
        conn.executemany("""
        INSERT INTO measurements
          (timestamp, station, lat, lon, pm25, pm10, no2, o3,
           wind_speed, wind_deg, temp, humidity, hour, day_of_week, month)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, rows)
        conn.commit()


def get_training_data():
    """
    Возвращает данные для обучения.
    Фича: текущие условия → таргет: pm25 через 24 часа (следующий день тот же час).
    Используем lag: pm25_lag1h, pm25_lag3h, pm25_lag6h, pm25_lag12h, pm25_lag24h.
    """
    import pandas as pd
    with sqlite3.connect(DB_PATH) as conn:
        df = pd.read_sql("""
        SELECT timestamp, station, pm25, wind_speed, wind_deg,
               temp, humidity, hour, day_of_week, month
        FROM measurements
        ORDER BY timestamp
        """, conn)
    return df


def get_row_count() -> int:
    with sqlite3.connect(DB_PATH) as conn:
        return conn.execute("SELECT COUNT(*) FROM measurements").fetchone()[0]