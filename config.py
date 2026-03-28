import os

OWM_KEY = os.getenv("OWM_KEY", "MISSING_KEY")
OPENAQ_KEY = os.getenv("OPENAQ_KEY", "MISSING_KEY")

LAT_CENTER = 40.1792
LON_CENTER = 44.5133
OUTPUT_FILE = "yerevan_air.html"

# Update interval in seconds (3600 = 1 hour)
DT = int(os.getenv("UPDATE_INTERVAL_SEC", "3600"))

# Physics: Adjusted for 1-hour steps
DECAY = 0.85     # More realistic: pollution persists longer in 1-hour steps
DIFFUSION = 0.001 # Slightly reduced for more coherent plumes
MAX_PARTICLES = 800

FORECAST_STEPS = 6  # 6 hours of visual lookahead
ALERT_THRESHOLD = 100

YEREVAN_STATION_IDS = [2960649, 2960634, 2960632]
# Telegram
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "MISSING_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "MISSING_ID")

# Ingestion: delay between OpenAQ per-station calls (0 = fastest)
OPENAQ_STATION_DELAY_SEC = float(os.getenv("OPENAQ_STATION_DELAY_SEC", "0"))

# Run heavy DB analytics (correlation + district ranking) every N cycles (1 = every cycle)
ANALYTICS_EVERY_N_CYCLES = max(1, int(os.getenv("ANALYTICS_EVERY_N_CYCLES", "1")))

# LSTM Monte Carlo dropout samples per horizon (lower = faster CPU inference)
LSTM_MC_SAMPLES = max(3, min(50, int(os.getenv("LSTM_MC_SAMPLES", "12"))))

# Rotate predictions eval log when larger than this (bytes)
PREDICTIONS_LOG_MAX_BYTES = int(os.getenv("PREDICTIONS_LOG_MAX_BYTES", str(5 * 1024 * 1024)))

# Forecast prediction weight (0.2 = 20% LSTM prediction, 80% current baseline)
FORECAST_PREDICTION_WEIGHT = float(os.getenv("FORECAST_PREDICTION_WEIGHT", "0.2"))
