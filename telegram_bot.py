"""
telegram_bot.py — Telegram bot for Yerevan Air alerts.
 
Features:
  - /status  — current AQI across all stations
  - /top      — top 5 most polluted stations right now
  - Alert on AQI threshold breach (triggered from core.py)
  - Morning digest at 08:00 Yerevan time
"""
 
import requests
import threading
import time
from datetime import datetime
import pytz
 
import config
 
TELEGRAM_API = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}"
YEREVAN_TZ   = pytz.timezone("Asia/Yerevan")
 
_last_digest_date = None
 
 
# ── Send helpers ──────────────────────────────────────────────────────────────
 
def send_message(text: str, with_keyboard: bool = False) -> bool:
    keyboard = {
        "keyboard": [[{"text": "/status"}, {"text": "/top"}]],
        "resize_keyboard": True,
        "persistent": True,
    } if with_keyboard else {"remove_keyboard": True}

    try:
        r = requests.post(
            f"{TELEGRAM_API}/sendMessage",
            json={
                "chat_id":      config.TELEGRAM_CHAT_ID,
                "text":         text,
                "parse_mode":   "HTML",
                "reply_markup": keyboard,
            },
            timeout=10,
        )
        return r.ok
    except Exception as e:
        print(f"  [Telegram] send error: {e}")
        return False 
 
# ── Message builders ──────────────────────────────────────────────────────────
 
def _aqi_emoji(aqi: int) -> str:
    if aqi <= 50:   return "🟢"
    if aqi <= 100:  return "🟡"
    if aqi <= 150:  return "🟠"
    if aqi <= 200:  return "🔴"
    if aqi <= 300:  return "🟣"
    return "⚫"
 
 
def build_status_message(df) -> str:
    from aqi import pm25_to_aqi
    lines = ["<b>🌆 Yerevan Air — current status</b>\n"]
    for _, row in df.iterrows():
        aqi, label, _ = pm25_to_aqi(row["pm25"])
        emoji = _aqi_emoji(aqi)
        name  = row["name"][:35]
        lines.append(f"{emoji} <b>{aqi}</b>  {name}  <i>PM2.5: {row['pm25']:.1f}</i>")
    avg_aqi = int(df.apply(lambda r: pm25_to_aqi(r["pm25"])[0], axis=1).mean())
    lines.append(f"\n📊 <b>City average AQI: {avg_aqi}</b>")
    lines.append(f"🕐 {datetime.now(YEREVAN_TZ).strftime('%H:%M  %d.%m.%Y')}")
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
    now   = datetime.now(YEREVAN_TZ)
    rows  = [(row["name"], pm25_to_aqi(row["pm25"])[0], row["pm25"])
             for _, row in df.iterrows()]
    rows.sort(key=lambda x: -x[1])
 
    avg_aqi = int(sum(r[1] for r in rows) / len(rows)) if rows else 0
    worst   = rows[0]  if rows else None
    best    = rows[-1] if rows else None
 
    lines = [
        f"<b>☀️ Good morning! Yerevan Air digest — {now.strftime('%d.%m.%Y')}</b>\n",
        f"📊 City average AQI: <b>{avg_aqi}</b>  {_aqi_emoji(avg_aqi)}",
    ]
    if worst:
        lines.append(f"🔴 Most polluted: <b>{worst[0][:30]}</b> — AQI {worst[1]}")
    if best:
        lines.append(f"🟢 Cleanest: <b>{best[0][:30]}</b> — AQI {best[1]}")
    lines.append(f"\n💡 Threshold alert set at AQI {config.ALERT_THRESHOLD}")
    return "\n".join(lines)
 
 
# ── Alert sender (called from core.py) ───────────────────────────────────────
 
def notify_alerts(alerts: list):
    """Call this from core.py when new alerts fire."""
    if not alerts:
        return
    send_message(build_alert_message(alerts))
 
 
# ── Command polling loop ──────────────────────────────────────────────────────
 
_last_update_id = 0
_df_ref = [None]  # mutable reference to latest df, updated by core
 
 
def set_latest_df(df):
    """Called from core.py each cycle to keep df fresh."""
    _df_ref[0] = df
 
 
def _handle_commands():
    global _last_update_id
    try:
        r = requests.get(
            f"{TELEGRAM_API}/getUpdates",
            params={"offset": _last_update_id + 1, "timeout": 30},
            timeout=35,
        ).json()
 
        for update in r.get("result", []):
            _last_update_id = update["update_id"]
            text = update.get("message", {}).get("text", "").strip().lower()
 
            if text in ("/status", "/start"):
                if _df_ref[0] is not None:
                    send_message(build_status_message(_df_ref[0]), with_keyboard=True)
 
            elif text == "/top":
                if _df_ref[0] is not None:
                    from aqi import pm25_to_aqi
                    df = _df_ref[0]
                    rows = sorted(
                        [(row["name"], pm25_to_aqi(row["pm25"])[0], row["pm25"])
                         for _, row in df.iterrows()],
                        key=lambda x: -x[1]
                    )[:5]
                    lines = ["<b>🏭 Top 5 most polluted stations</b>\n"]
                    for i, (name, aqi, pm25) in enumerate(rows, 1):
                        lines.append(f"{i}. {_aqi_emoji(aqi)} <b>{name[:30]}</b> — AQI {aqi}  PM2.5: {pm25:.1f}")
                    send_message("\n".join(lines))
                else:
                    send_message("⏳ Still loading data, try again in 30 seconds.")
 
            elif text == "/help":
                send_message(
                    "<b>Yerevan Air Bot commands</b>\n\n"
                    "/status — current AQI for all stations\n"
                    "/top    — top 5 most polluted stations\n"
                    "/help   — this message\n\n"
                    "🔔 Automatic alerts when AQI exceeds threshold."
                )
 
    except Exception as e:
        print(f"  [Telegram] poll error: {e}")
 
 
def _morning_digest_loop():
    """Sends a digest every day at 08:00 Yerevan time."""
    global _last_digest_date
    while True:
        now = datetime.now(YEREVAN_TZ)
        if now.hour == 8 and now.date() != _last_digest_date:
            if _df_ref[0] is not None:
                send_message(build_digest_message(_df_ref[0]))
                _last_digest_date = now.date()
        time.sleep(60)
 
 
def _polling_loop():
    while True:
        _handle_commands()
 
 
def start():
    """Start bot threads. Call once at server startup."""
    threading.Thread(target=_polling_loop,       daemon=True).start()
    threading.Thread(target=_morning_digest_loop, daemon=True).start()
    print("  [Telegram] bot started — polling for commands")
    send_message("🚀 <b>Yerevan Air bot started!</b>\nSend /status to get current AQI.", with_keyboard=True)