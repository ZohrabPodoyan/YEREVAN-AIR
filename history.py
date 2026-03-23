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

    # Собираем все временные метки по порядку (O(n))
    time_to_vals: dict[str, list] = {}
    for dq in _history.values():
        for p in dq:
            time_to_vals.setdefault(p["t"], []).append(p["aqi"])

    result = [
        {"t": t, "aqi": int(sum(vals) / len(vals))}
        for t, vals in time_to_vals.items()
    ]
    return result[-48:]