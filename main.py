"""
main.py — Main simulation loop
Run: python main.py
"""

import time
from datetime import datetime

import config
from database  import init_db, get_training_data, get_row_count
from predictor import train
from core import run_cycle

print("╔══════════════════════════════════════════════╗")
print("║  YEREVAN AIR POLLUTION SIMULATION  v4.0      ║")
print("║  Air: OpenAQ v3  ·  Wind: OWM                ║")
print("║  AQI · History · Alerts · Forecast           ║")
print("╚══════════════════════════════════════════════╝\n")

particles = []

# Initialize database
init_db()
existing = get_row_count()
if existing >= 200:
    print(f"  Found {existing} records → training model...")
    train(get_training_data())
print("  DB initialized → air_data.db")

while True:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"\n[{ts}] ── Update cycle ──")

    particles, html = run_cycle(particles)

    with open(config.OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"[{datetime.now().strftime('%H:%M:%S')}] ✓ {config.OUTPUT_FILE}")
    print(f"  Next update in {config.DT // 60} min...\n")
    time.sleep(config.DT)