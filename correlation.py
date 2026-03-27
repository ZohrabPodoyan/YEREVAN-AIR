"""
correlation.py — AQI correlation with time of day and day of week
"""
from database import connect_db

DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def get_hourly_avg() -> list[dict]:
    """Average PM2.5 by hour (0-23)."""

    with connect_db() as conn:
        rows = conn.execute("""
            SELECT hour, AVG(pm25) as avg_pm25, COUNT(*) as cnt
            FROM measurements
            WHERE pm25 > 0 AND pm25 < 500
            GROUP BY hour
            ORDER BY hour
        """).fetchall()

    return [
        {"hour": row[0], "pm25": round(row[1], 1), "cnt": row[2]}
        for row in rows
    ]


def get_daily_avg() -> list[dict]:
    """Average PM2.5 by day of week (0=Mon, 6=Sun)."""
    with connect_db() as conn:
        rows = conn.execute("""
            SELECT day_of_week, AVG(pm25) as avg_pm25, COUNT(*) as cnt
            FROM measurements
            WHERE pm25 > 0 AND pm25 < 500
            GROUP BY day_of_week
            ORDER BY day_of_week
        """).fetchall()

    return [
        {
            "day": row[0],
            "name": DAY_NAMES[row[0]],
            "pm25": round(row[1], 1),
            "cnt": row[2]
        }
        for row in rows
    ]


def get_correlation_data() -> dict:
    """Returns all correlation data."""
    hourly = get_hourly_avg()
    daily  = get_daily_avg()

    # Peak hours
    if hourly:
        worst_hour = max(hourly, key=lambda x: x["pm25"])
        best_hour  = min(hourly, key=lambda x: x["pm25"])
    else:
        worst_hour = best_hour = None

    # Best/worst day
    if daily:
        worst_day = max(daily, key=lambda x: x["pm25"])
        best_day  = min(daily, key=lambda x: x["pm25"])
    else:
        worst_day = best_day = None

    return {
        "hourly":     hourly,
        "daily":      daily,
        "worst_hour": worst_hour,
        "best_hour":  best_hour,
        "worst_day":  worst_day,
        "best_day":   best_day,
    }