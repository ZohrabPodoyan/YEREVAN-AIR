"""
history.py — хранение истории AQI (последние 4 часа)
"""
from collections import deque
from datetime import datetime

MAX_POINTS = 288  # 24 часа при шаге 5 мин

_history: dict[str, deque] = {}


def record(df) -> None:
    from aqi import pm25_to_aqi
    ts = datetime.now().strftime("%H:%M")
    for _, row in df.iterrows():
        name = row["name"]
        aqi, _, _ = pm25_to_aqi(row["pm25"])
        if name not in _history:
            _history[name] = deque(maxlen=MAX_POINTS)
        _history[name].append({"t": ts, "aqi": aqi})


def get_city_history() -> list[dict]:
    """Усреднённая история по всем станциям, последние 48 точек (4 часа)."""
    if not _history:
        return []
    all_times, seen = [], set()
    for dq in _history.values():
        for p in dq:
            if p["t"] not in seen:
                all_times.append(p["t"])
                seen.add(p["t"])
    result = []
    for t in all_times:
        vals = []
        for dq in _history.values():
            for p in dq:
                if p["t"] == t:
                    vals.append(p["aqi"])
                    break
        if vals:
            result.append({"t": t, "aqi": int(sum(vals) / len(vals))})
    return result[-48:]