"""
server.py — Flask сервер для деплоя.
Симуляция в фоне, HTML отдаётся по HTTP.
"""
import threading
import time
import os
from flask import Flask, send_file, jsonify
from datetime import datetime
from pathlib import Path

import config
from fetcher   import fetch_air_data, fetch_wind_data
from physics   import wind_displacement, step_particles, emit_particles, trim_particles
from renderer  import render
from history   import record
from alerts    import check_alerts
from forecast  import run_forecast
from database  import init_db, save_measurements, get_training_data, get_row_count
from predictor import train, predict, save_prediction_for_eval, get_prediction_vs_reality
from correlation import get_correlation_data

app = Flask(__name__)
OUTPUT_FILE = Path("yerevan_air.html")

state = {"particles": [], "last_update": None, "running": False}


def simulation_loop():
    state["running"] = True
    init_db()

    existing = get_row_count()
    if existing >= 200:
        train(get_training_data())

    while True:
        try:
            df   = fetch_air_data()
            wind = fetch_wind_data()

            save_measurements(df, wind)
            row_count = get_row_count()

            if row_count % 100 == 0 and row_count > 0:
                train(get_training_data())

            prediction  = predict(get_training_data(), wind)
            save_prediction_for_eval(prediction, datetime.now().isoformat())
            vs_reality  = get_prediction_vs_reality(get_training_data())

            record(df)
            new_alerts      = check_alerts(df)
            forecast_frames = run_forecast(state["particles"], df, wind)

            d_lat, d_lon = wind_displacement(wind["wind_speed"], wind["wind_deg"], config.DT)
            state["particles"]  = step_particles(state["particles"], d_lat, d_lon)
            state["particles"] += emit_particles(df)
            state["particles"]  = trim_particles(state["particles"])
            correlation = get_correlation_data()
            html = render(particles, df, wind, new_alerts, forecast_frames, prediction, vs_reality, correlation)
            OUTPUT_FILE.write_text(html, encoding="utf-8")
            state["last_update"] = datetime.now().isoformat()

        except Exception as ex:
            print(f"[ERROR] {ex}")

        time.sleep(config.DT)


@app.route("/")
def index():
    if OUTPUT_FILE.exists():
        return send_file(OUTPUT_FILE)
    return "<h1>Initializing... refresh in 30 seconds</h1>", 503

@app.route('/favicon.ico')
def favicon():
    return '', 204

@app.route("/health")
def health():
    return jsonify({
        "status":      "ok",
        "last_update": state["last_update"],
        "particles":   len(state["particles"]),
    })


if __name__ == "__main__":
    thread = threading.Thread(target=simulation_loop, daemon=True)
    thread.start()

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
