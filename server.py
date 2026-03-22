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
from district_ranking import get_district_ranking
from weather_forecast import get_weather_forecast
from anomaly import detect_anomalies
from core import run_cycle

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
            state["particles"], html = run_cycle(state["particles"])
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
