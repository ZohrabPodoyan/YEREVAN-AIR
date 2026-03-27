"""
weather_forecast.py - Weather and AQI forecast for 3 days from OWM
"""
import logging
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from aqi import pm25_to_aqi
import config

logger = logging.getLogger(__name__)


def _session():
    s = requests.Session()
    retries = Retry(total=3, backoff_factor=0.4, status_forcelist=(502, 503, 504))
    s.mount("https://", HTTPAdapter(max_retries=retries))
    s.mount("http://", HTTPAdapter(max_retries=retries))
    return s


def get_weather_forecast() -> list[dict]:
    """OWM forecast 5 days / 3 hours -> take one per day."""
    try:
        r = _session().get(
            "http://api.openweathermap.org/data/2.5/forecast",
            params={
                "lat":   config.LAT_CENTER,
                "lon":   config.LON_CENTER,
                "appid": config.OWM_KEY,
                "units": "metric",
                "cnt":   24,
            },
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()

        days = {}
        for item in data.get("list", []):
            date = item["dt_txt"][:10]
            hour = int(item["dt_txt"][11:13])
            if hour != 12:
                continue

            wind_speed = item.get("wind", {}).get("speed", 0)
            wind_deg   = item.get("wind", {}).get("deg", 0)
            temp       = item.get("main", {}).get("temp", 0)
            humidity   = item.get("main", {}).get("humidity", 0)
            weather    = item.get("weather", [{}])[0]
            icon       = weather.get("main", "Clear")
            desc       = weather.get("description", "")
            clouds     = item.get("clouds", {}).get("all", 0)
            rain       = item.get("rain", {}).get("3h", 0)

            base_pm25 = 20.0
            if rain > 0:
                base_pm25 *= 0.5
            if wind_speed > 5:
                base_pm25 *= 0.7
            if wind_speed < 1:
                base_pm25 *= 1.4
            if humidity > 80:
                base_pm25 *= 1.2
            if clouds < 20:
                base_pm25 *= 0.9

            aqi, label, color = pm25_to_aqi(round(base_pm25, 1))

            days[date] = {
                "date":       date,
                "temp":       round(temp, 1),
                "humidity":   humidity,
                "wind_speed": round(wind_speed, 1),
                "wind_deg":   wind_deg,
                "icon":       icon,
                "desc":       desc,
                "clouds":     clouds,
                "rain":       rain,
                "est_pm25":   round(base_pm25, 1),
                "est_aqi":    aqi,
                "est_label":  label,
                "est_color":  color,
            }

        return list(days.values())[:3]

    except Exception as e:
        logger.warning("OWM Forecast error: %s", e)
        return []
