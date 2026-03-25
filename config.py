import os

OWM_KEY = os.getenv("OWM_KEY", "MISSING_KEY")
OPENAQ_KEY = os.getenv("OPENAQ_KEY", "MISSING_KEY")

LAT_CENTER = 40.1792
LON_CENTER = 44.5133
OUTPUT_FILE = "yerevan_air.html"

# Update interval in seconds (3600 = 1 hour)
DT = 3600 

# Physics: Adjusted for 1-hour steps
DECAY = 0.5       # Stronger decay because 1 hour is a long time
DIFFUSION = 0.002 # Increased spread to match the 1-hour jump
MAX_PARTICLES = 800

FORECAST_STEPS = 6 # 6 hours of visual lookahead
ALERT_THRESHOLD = 100

YEREVAN_STATION_IDS = [2960649, 2960634, 2960632]
# Telegram
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "MISSING_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "MISSING_ID")
