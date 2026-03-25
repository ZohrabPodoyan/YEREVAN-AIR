"""
weather_forecast.py - Weather and AQI forecast for 3 days from OWM
"""
import requests
from aqi import pm25_to_aqi
import config

def get_weather_forecast() -> list[dict]: # OWM forecast 5 days / 3 hours -> take one per day.
    """OWM forecast 5 days / 3 hours -> take one per day."""
    try:
        r = requests.get(
            "http://api.openweathermap.org/data/2.5/forecast",
            params={
                "lat":   config.LAT_CENTER,
                "lon":   config.LON_CENTER,
                "appid": config.OWM_KEY,
                "units": "metric",
                "cnt":   24,  # 24 * 3h = 3 дня
            },
            timeout=10,
        ).json()

        days = {}
        for item in r.get("list", []):
            date = item["dt_txt"][:10]
            hour = int(item["dt_txt"][11:13])
            if hour != 12:
                continue  # Take only noon

            wind_speed = item.get("wind", {}).get("speed", 0)
            wind_deg   = item.get("wind", {}).get("deg", 0)
            temp       = item.get("main", {}).get("temp", 0)
            humidity   = item.get("main", {}).get("humidity", 0)
            weather    = item.get("weather", [{}])[0]
            icon       = weather.get("main", "Clear")
            desc       = weather.get("description", "")
            clouds     = item.get("clouds", {}).get("all", 0)
            rain       = item.get("rain", {}).get("3h", 0) 

            # PM2.5 estimation based on weather
            # Rain cleans the air, wind disperses
            base_pm25 = 20.0
            if rain > 0:
                base_pm25 *= 0.5   # Rain reduces PM2.5
            if wind_speed > 5:
                base_pm25 *= 0.7   # Strong wind disperses
            if wind_speed < 1:
                base_pm25 *= 1.4   # Calm = stagnation
            if humidity > 80:
                base_pm25 *= 1.2   # высокая влажность
            if clouds < 20:
                base_pm25 *= 0.9   # ясно

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
        print(f"  [OWM Forecast] error: {e}")
        return []