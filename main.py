"""
main.py — главный цикл симуляции
Запуск: python main.py
"""

import time
from datetime import datetime

import config
from fetcher  import fetch_air_data, fetch_wind_data
from physics  import wind_displacement, step_particles, emit_particles, trim_particles
from renderer import render
from history  import record
from alerts   import check_alerts
from forecast import run_forecast
from database  import init_db, save_measurements, get_training_data, get_row_count
from predictor import train, predict, save_prediction_for_eval, get_prediction_vs_reality
from correlation import get_correlation_data
from district_ranking import get_district_ranking
from weather_forecast import get_weather_forecast
from anomaly import detect_anomalies
from core import run_cycle

print("╔══════════════════════════════════════════════╗")
print("║  YEREVAN AIR POLLUTION SIMULATION  v4.0      ║")
print("║  Air: OpenAQ v3  ·  Wind: OWM                ║")
print("║  AQI · History · Alerts · Forecast           ║")
print("╚══════════════════════════════════════════════╝\n")

particles = []

# Инициализируем БД
init_db()
existing = get_row_count()
if existing >= 200:
    print(f"  Найдено {existing} записей → обучаю модель...")
    train(get_training_data())
print("  DB initialized → air_data.db")

while True:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"\n[{ts}] ── Цикл обновления ──")
    
    particles, html = run_cycle(particles)
    
    with open(config.OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] ✓ {config.OUTPUT_FILE}")
    print(f"  Следующее обновление через {config.DT // 60} мин...\n")
    time.sleep(config.DT)