"""
database.py - Collects historical data in SQLite for model training.

Measurements table:
  timestamp, station_name, lat, lon,
  pm25, pm10, no2, o3,
  wind_speed, wind_deg, temp, humidity,
  hour, day_of_week, month
"""

import sqlite3
import time
import os
import pandas as pd
from datetime import datetime
from pathlib import Path

DB_PATH = Path(os.environ.get("DB_PATH", Path(__file__).parent / "air_data.csv"))

SQLITE_BUSY_RETRIES = 5


def connect_db():
    """SQLite connection with WAL and busy timeout (use as context manager)."""
    return _connect()


def _connect():
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def init_db():
    with _connect() as conn:
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
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_measurements_ts ON measurements(timestamp)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_measurements_station_ts ON measurements(station, timestamp)"
        )
        conn.commit()


def save_measurements(df, wind: dict):
    """Saves current data for all stations."""
    now = datetime.now().replace(microsecond=0)
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
    sql = """
        INSERT INTO measurements
          (timestamp, station, lat, lon, pm25, pm10, no2, o3,
           wind_speed, wind_deg, temp, humidity, hour, day_of_week, month)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """
    for attempt in range(SQLITE_BUSY_RETRIES):
        try:
            with _connect() as conn:
                conn.executemany(sql, rows)
                conn.commit()
            return
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower() and attempt < SQLITE_BUSY_RETRIES - 1:
                time.sleep(0.05 * (2 ** attempt))
                continue
            raise


def get_training_data():
    """
    Returns data for training.
    Feature: current conditions -> target: pm25 after 24 hours (next day same hour).
    Using lag: pm25_lag1h, pm25_lag3h, pm25_lag6h, pm25_lag12h, pm25_lag24h.
    """
    with _connect() as conn:
        df = pd.read_sql("""
        SELECT * FROM (
            SELECT timestamp, station, pm25, wind_speed, wind_deg,
                   temp, humidity, hour, day_of_week, month
            FROM measurements
            ORDER BY timestamp DESC
            LIMIT 10000
        ) ORDER BY timestamp ASC
        """, conn)
    return df


def get_row_count() -> int:
    with _connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM measurements").fetchone()[0]
