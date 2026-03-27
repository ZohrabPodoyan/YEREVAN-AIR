"""
server.py - Flask server for deployment.
Simulation in background, HTML is served via HTTP.
"""
import csv
import io
import logging
import os
import sqlite3
import threading
import time
import traceback

import config
from flask import Flask, Response, jsonify, send_file, stream_with_context
from datetime import datetime
from pathlib import Path
from database import init_db, get_training_data, get_row_count, DB_PATH
from predictor import train
from core import run_cycle

def _log_level():
    name = os.getenv("LOG_LEVEL", "INFO").upper()
    return getattr(logging, name, logging.INFO)


logging.basicConfig(
    level=_log_level(),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
OUTPUT_FILE = Path(config.OUTPUT_FILE)

_state_lock = threading.Lock()
state = {"particles": [], "last_update": None, "running": False, "html": None}

_bg_started = False
_bg_lock = threading.Lock()


def ensure_background_worker():
    """
    Start the simulation + Telegram loop once per process.
    Must run under Gunicorn (not only `python server.py`). Use --workers 1 on Gunicorn
    so only one loop runs.
    Set YEREVAN_SKIP_BACKGROUND=1 to disable (e.g. tests importing this module).
    """
    global _bg_started
    if os.getenv("YEREVAN_SKIP_BACKGROUND") == "1":
        return
    with _bg_lock:
        if _bg_started:
            return
        _bg_started = True
        thread = threading.Thread(target=simulation_loop, daemon=True)
        thread.start()
        logger.info("Background worker thread started")


def simulation_loop():
    with _state_lock:
        state["running"] = True
    init_db()
    existing = get_row_count()
    if existing >= 200:
        train(get_training_data())

    from telegram_bot import start as start_bot
    start_bot()

    while True:
        try:
            particles, html = run_cycle(state.get("particles", []))
            OUTPUT_FILE.write_text(html, encoding="utf-8")
            with _state_lock:
                state["particles"] = particles
                state["html"] = html
                state["last_update"] = datetime.now().isoformat()
        except Exception as ex:
            logger.exception("Simulation cycle failed: %s", ex)
            traceback.print_exc()
        time.sleep(config.DT)


@app.route("/")
def index():
    with _state_lock:
        html = state.get("html")
    if html:
        return html
    if OUTPUT_FILE.exists():
        return send_file(OUTPUT_FILE)
    return "<h1>Initializing... refresh in 30 seconds</h1>", 503


@app.route('/favicon.ico')
def favicon():
    return '', 204


@app.route("/health")
def health():
    with _state_lock:
        payload = {
            "status":      "ok",
            "last_update": state.get("last_update"),
            "particles":   len(state.get("particles") or []),
        }
    return jsonify(payload)


@app.route("/ready")
def ready():
    """Readiness: first HTML produced."""
    with _state_lock:
        ok = bool(state.get("html")) or OUTPUT_FILE.exists()
    return jsonify({"ready": ok}), 200 if ok else 503


def _csv_row_generator():
    conn = sqlite3.connect(str(DB_PATH), timeout=60.0)
    conn.execute("PRAGMA busy_timeout=60000")
    try:
        cur = conn.execute("SELECT * FROM measurements ORDER BY id")
        cols = [d[0] for d in cur.description]
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(cols)
        yield buf.getvalue()
        for row in cur:
            buf.seek(0)
            buf.truncate(0)
            w.writerow(row)
            yield buf.getvalue()
    finally:
        conn.close()


@app.route('/export-db')
def export_db():
    return Response(
        stream_with_context(_csv_row_generator()),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=air_data.csv'}
    )


ensure_background_worker()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    # Dev only; production should use: gunicorn server:app --bind 0.0.0.0:$PORT --workers 1
    app.run(host="0.0.0.0", port=port, use_reloader=False, threaded=True)
