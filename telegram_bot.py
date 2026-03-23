"""
telegram_bot.py — Telegram bot for Yerevan Air alerts.
 
Features:
  - Inline keyboard with 5 buttons (always visible)
  - /status   — full AQI across all stations
  - /top      — top 5 most polluted stations
  - /best     — top 5 cleanest stations
  - /weather  — current wind, temp, humidity
  - /help     — command list
  - Alert on AQI threshold breach
  - Morning digest at 08:00 Yerevan time
"""

import requests
import threading
import time
from datetime import datetime
import pytz

import config

TELEGRAM_API = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}"
YEREVAN_TZ = pytz.timezone("Asia/Yerevan")

_last_digest_date = None
_last_update_id = 0
_df_ref = [None]
_wind_ref = [None]

INLINE_KEYBOARD = {
    "inline_keyboard": [
        [
            {"text": "📊 Status",  "callback_data": "status"},
            {"text": "🏭 Worst 5", "callback_data": "top"},
            {"text": "🌿 Best 5",  "callback_data": "best"},
        ],
        [
            {"text": "🌬 Weather", "callback_data": "weather"},
            {"text": "ℹ️ Help",    "callback_data": "help"},
        ],
    ]
}


# ── Send helpers ──────────────────────────────────────────────────────────────

def send_message(text: str, chat_id: int = None) -> bool:
    try:
        r = requests.post(
            f"{TELEGRAM_API}/sendMessage",
            json={
                "chat_id":      chat_id or config.TELEGRAM_CHAT_ID,
                "text":         text,
                "parse_mode":   "HTML",
                "reply_markup": INLINE_KEYBOARD,
            },
            timeout=10,
        )
        return r.ok
    except Exception as e:
        print(f"  [Telegram] send error: {e}")
        return False


def answer_callback(callback_query_id: str, text: str = ""):
    """Acknowledge the button tap (removes loading spinner)."""
    try:
        requests.post(
            f"{TELEGRAM_API}/answerCallbackQuery",
            json={"callback_query_id": callback_query_id, "text": text},
            timeout=5,
        )
    except Exception:
        pass


# ── AQI helpers ───────────────────────────────────────────────────────────────

def _aqi_emoji(aqi: int) -> str:
    if aqi <= 50:
        return "🟢"
    if aqi <= 100:
        return "🟡"
    if aqi <= 150:
        return "🟠"
    if aqi <= 200:
        return "🔴"
    if aqi <= 300:
        return "🟣"
    return "⚫"


def _wind_direction(deg: float) -> str:
    dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    return dirs[int((deg + 22.5) / 45) % 8]


# ── Message builders ──────────────────────────────────────────────────────────

def build_status_message(df) -> str:
    from aqi import pm25_to_aqi
    lines = ["<b>🌆 Yerevan Air — current status</b>\n"]
    for _, row in df.iterrows():
        aqi, label, _ = pm25_to_aqi(row["pm25"])
        emoji = _aqi_emoji(aqi)
        name = row["name"][:32]
        lines.append(
            f"{emoji} <b>{aqi:3d}</b>  {name}  <i>{row['pm25']:.1f} μg/m³</i>")
    avg_aqi = int(df.apply(lambda r: pm25_to_aqi(r["pm25"])[0], axis=1).mean())
    lines.append(
        f"\n📊 <b>City average AQI: {avg_aqi}</b>  {_aqi_emoji(avg_aqi)}")
    lines.append(f"🕐 {datetime.now(YEREVAN_TZ).strftime('%H:%M  %d.%m.%Y')}")
    return "\n".join(lines)


def build_top_message(df, worst: bool = True) -> str:
    from aqi import pm25_to_aqi
    rows = sorted(
        [(row["name"], pm25_to_aqi(row["pm25"])[0], row["pm25"])
         for _, row in df.iterrows()],
        key=lambda x: -x[1] if worst else x[1]
    )[:5]
    title = "🏭 <b>Top 5 most polluted stations</b>" if worst else "🌿 <b>Top 5 cleanest stations</b>"
    lines = [title + "\n"]
    for i, (name, aqi, pm25) in enumerate(rows, 1):
        lines.append(
            f"{i}. {_aqi_emoji(aqi)} <b>{name[:30]}</b>\n    AQI {aqi}  ·  PM2.5: {pm25:.1f} μg/m³")
    lines.append(f"\n🕐 {datetime.now(YEREVAN_TZ).strftime('%H:%M  %d.%m.%Y')}")
    return "\n".join(lines)


def build_weather_message(wind: dict) -> str:
    speed = wind.get("wind_speed", 0)
    deg = wind.get("wind_deg", 0)
    temp = wind.get("temp", 0)
    hum = wind.get("humidity", 0)
    direction = _wind_direction(deg)
    lines = [
        "<b>🌤 Current weather — Yerevan</b>\n",
        f"🌡 Temperature:  <b>{temp:.1f} °C</b>",
        f"💧 Humidity:     <b>{hum:.0f}%</b>",
        f"🌬 Wind speed:   <b>{speed:.1f} m/s</b>",
        f"🧭 Direction:    <b>{direction} ({deg:.0f}°)</b>",
        f"\n🕐 {datetime.now(YEREVAN_TZ).strftime('%H:%M  %d.%m.%Y')}",
    ]
    return "\n".join(lines)


def build_alert_message(alerts: list) -> str:
    lines = ["<b>⚠️ Air quality alert!</b>\n"]
    for a in alerts:
        emoji = _aqi_emoji(a["aqi"])
        lines.append(
            f"{emoji} <b>{a['name'][:35]}</b>\n"
            f"   AQI {a['aqi']} — {a['label']}\n"
            f"   PM2.5: {a['pm25']} μg/m³"
        )
    return "\n".join(lines)


def build_digest_message(df) -> str:
    from aqi import pm25_to_aqi
    now = datetime.now(YEREVAN_TZ)
    rows = [(row["name"], pm25_to_aqi(row["pm25"])[0], row["pm25"])
            for _, row in df.iterrows()]
    rows.sort(key=lambda x: -x[1])
    avg_aqi = int(sum(r[1] for r in rows) / len(rows)) if rows else 0
    worst = rows[0] if rows else None
    best = rows[-1] if rows else None
    lines = [
        f"<b>☀️ Good morning! Yerevan Air digest — {now.strftime('%d.%m.%Y')}</b>\n",
        f"📊 City average AQI: <b>{avg_aqi}</b>  {_aqi_emoji(avg_aqi)}",
    ]
    if worst:
        lines.append(
            f"🔴 Most polluted: <b>{worst[0][:30]}</b> — AQI {worst[1]}")
    if best:
        lines.append(f"🟢 Cleanest:      <b>{best[0][:30]}</b> — AQI {best[1]}")
    lines.append(f"\n💡 Alert threshold: AQI {config.ALERT_THRESHOLD}")
    return "\n".join(lines)


def build_help_message() -> str:
    return (
        "<b>ℹ️ Yerevan Air Bot</b>\n\n"
        "📊 <b>Status</b>  — AQI for all stations\n"
        "🏭 <b>Worst 5</b> — most polluted right now\n"
        "🌿 <b>Best 5</b>  — cleanest right now\n"
        "🌬 <b>Weather</b> — wind, temp, humidity\n\n"
        "🔔 Auto alerts when AQI exceeds threshold\n"
        "☀️ Morning digest every day at 08:00\n\n"
        f"⚙️ Alert threshold: AQI {config.ALERT_THRESHOLD}\n"
        "📡 Data: OpenAQ v3 · OpenWeatherMap"
    )


# ── Response dispatcher ───────────────────────────────────────────────────────

def _dispatch(action: str, chat_id: int):
    loading = _df_ref[0] is None
    if action == "status":
        msg = build_status_message(
            _df_ref[0]) if not loading else "⏳ Loading data, try again in 30s."
    elif action == "top":
        msg = build_top_message(
            _df_ref[0], worst=True) if not loading else "⏳ Loading data, try again in 30s."
    elif action == "best":
        msg = build_top_message(
            _df_ref[0], worst=False) if not loading else "⏳ Loading data, try again in 30s."
    elif action == "weather":
        msg = build_weather_message(
            _wind_ref[0]) if _wind_ref[0] else "⏳ Loading data, try again in 30s."
    elif action == "help":
        msg = build_help_message()
    else:
        return
    send_message(msg, chat_id=chat_id)


# ── Alert & digest senders ────────────────────────────────────────────────────

def notify_alerts(alerts: list):
    """Called from core.py when new alerts fire."""
    if not alerts:
        return
    send_message(build_alert_message(alerts))


def set_latest_df(df):
    """Called from core.py each cycle."""
    _df_ref[0] = df


def set_latest_wind(wind: dict):
    """Called from core.py each cycle."""
    _wind_ref[0] = wind


# ── Polling loop ──────────────────────────────────────────────────────────────

def _handle_updates():
    global _last_update_id
    try:
        r = requests.get(
            f"{TELEGRAM_API}/getUpdates",
            params={"offset": _last_update_id + 1, "timeout": 30},
            timeout=35,
        ).json()

        for update in r.get("result", []):
            _last_update_id = update["update_id"]

            # Inline button tap
            if "callback_query" in update:
                cq = update["callback_query"]
                action = cq["data"]
                chat_id = cq["message"]["chat"]["id"]
                answer_callback(cq["id"])
                _dispatch(action, chat_id)

            # Text command
            elif "message" in update:
                text = update["message"].get("text", "").strip().lower()
                chat_id = update["message"]["chat"]["id"]
                if text in ("/start", "/status"):
                    _dispatch("status", chat_id)
                elif text == "/top":
                    _dispatch("top", chat_id)
                elif text == "/best":
                    _dispatch("best", chat_id)
                elif text == "/weather":
                    _dispatch("weather", chat_id)
                elif text == "/help":
                    _dispatch("help", chat_id)

    except Exception as e:
        print(f"  [Telegram] poll error: {e}")


def _polling_loop():
    while True:
        _handle_updates()


def _morning_digest_loop():
    global _last_digest_date
    while True:
        now = datetime.now(YEREVAN_TZ)
        if now.hour == 8 and now.date() != _last_digest_date:
            if _df_ref[0] is not None:
                send_message(build_digest_message(_df_ref[0]))
                _last_digest_date = now.date()
        time.sleep(60)


# ── Startup ───────────────────────────────────────────────────────────────────

def start():
    """Start bot threads. Call once at server startup."""
    threading.Thread(target=_polling_loop,        daemon=True).start()
    threading.Thread(target=_morning_digest_loop, daemon=True).start()
    print("  [Telegram] bot started — polling for commands")
    send_message("🚀 <b>Yerevan Air bot started!</b>\nUse the buttons below.")
