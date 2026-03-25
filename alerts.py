"""
alerts.py - Alerts when AQI threshold is exceeded
"""
import config

_last_status: dict[str, str] = {}


def check_alerts(df) -> list[dict]: 
    """
    Returns new alerts only when crossing the threshold.
    [{name, aqi, label, color, pm25}] 
    """ 
    from aqi import pm25_to_aqi
    alerts = []
    for _, row in df.iterrows():
        name = row["name"]
        aqi, label, color = pm25_to_aqi(row["pm25"])
        if aqi == 500:
            continue
        exceeded = aqi >= config.ALERT_THRESHOLD
        prev = _last_status.get(name, "ok")
        if exceeded and prev == "ok":
            alerts.append({
                "name": name, "aqi": aqi,
                "label": label, "color": color,
                "pm25": round(row["pm25"], 1),
            })
        _last_status[name] = "alert" if exceeded else "ok"
    return alerts
