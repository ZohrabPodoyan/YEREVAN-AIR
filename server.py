"""
server.py — Flask сервер для деплоя.
Симуляция в фоне, HTML отдаётся по HTTP.
"""
import threading
import time
import os
import traceback
import config
from flask import Flask, send_file, jsonify
from datetime import datetime
from pathlib import Path
from database import init_db, get_training_data, get_row_count
from predictor import train
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

    from telegram_bot import start as start_bot  
    start_bot() 

    while True:
        try:
            state["particles"], html = run_cycle(state["particles"])
            OUTPUT_FILE.write_text(html, encoding="utf-8")
            state["last_update"] = datetime.now().isoformat()
        except Exception as ex:
            print(f"[ERROR] {ex}")
            traceback.print_exc()
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

@app.route('/export-db')
def export_db():
    import sqlite3
    import io
    import csv
    from flask import Response
    
    with sqlite3.connect('/data/air_data.db' if os.path.exists('/data') else 'air_data.db') as conn:
        cursor = conn.execute("SELECT * FROM measurements")
        rows = cursor.fetchall()
        headers = [d[0] for d in cursor.description]
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    writer.writerows(rows)
    
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=air_data.csv'}
    )


if __name__ == "__main__":
    thread = threading.Thread(target=simulation_loop, daemon=True)
    thread.start()

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
