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

    df   = fetch_air_data()
    wind = fetch_wind_data()
    # Сохраняем в БД
    save_measurements(df, wind)
    row_count = get_row_count()
    print(f"  DB: {row_count} записей")

    # Переобучение каждые 100 новых записей
    if row_count % 100 == 0 and row_count > 0:
        print("  [LSTM] Переобучение...")
        train(get_training_data())

    # Предсказание
    prediction = predict(get_training_data(), wind)
    save_prediction_for_eval(prediction, datetime.now().isoformat())

    # Сравнение prediction vs reality
    vs_reality = get_prediction_vs_reality(get_training_data())
    for p in prediction:
        print(f"  Pred {p['horizon']:4s}: PM2.5={p['pm25']:5.1f}±{p['pm25_hi']-p['pm25']:.1f} "
              f"AQI={p['aqi']:3d} conf={p['confidence']:.0%} [{p['model']}]")
    record(df)

    new_alerts = check_alerts(df)
    for a in new_alerts:
        print(f"  ⚠ ALERT: {a['name']} AQI={a['aqi']} [{a['label']}]")

    print(f"  Running {config.FORECAST_STEPS}-step forecast...")
    forecast_frames = run_forecast(particles, df, wind)
    print(f"  Forecast: {len(forecast_frames)} frames, "
          f"AQI in 1h = {forecast_frames[-1]['avg_aqi']}")

    d_lat, d_lon = wind_displacement(wind["wind_speed"], wind["wind_deg"], config.DT)
    particles    = step_particles(particles, d_lat, d_lon)
    particles   += emit_particles(df)
    particles    = trim_particles(particles)

    html = render(particles, df, wind, new_alerts, forecast_frames, prediction, vs_reality)
    with open(config.OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"[{datetime.now().strftime('%H:%M:%S')}] ✓ {config.OUTPUT_FILE} "
          f"({len(particles)} particles)")
    print(f"  Следующее обновление через {config.DT // 60} мин...\n")

    time.sleep(config.DT)