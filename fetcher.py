"""
fetcher.py — получение данных из двух источников:
  • OpenAQ v3   → PM2.5, PM10, NO2, O3  (реальные станции)
  • OWM         → скорость/направление ветра, температура, влажность

Баги исправлены:
  - coordinates + radius давал 422 (order_by=distance несовместим) → используем bbox
  - /latest не содержит parameter.name → берём sensor_id маппинг из /locations/{id}
"""

import time
import requests
import pandas as pd

import config

OPENAQ_BASE    = "https://api.openaq.org/v3"
OPENAQ_HEADERS = {
    "X-API-Key": config.OPENAQ_KEY,
    "Accept":    "application/json",
}

PARAM_MAP = {
    "pm2.5": "pm25",
    "pm25":  "pm25",
    "pm10":  "pm10",
    "no2":   "no2",
    "o3":    "o3",
}


def _search_locations_bbox(lat: float, lon: float, delta: float = 0.3) -> list[dict]:
    """
    GET /v3/locations?bbox=minLon,minLat,maxLon,maxLat
    delta=0.3° ≈ 33 км — покрывает весь Ереван.
    Сразу строим маппинг sensor_id → параметр из sensors[].
    """
    bbox = f"{lon-delta},{lat-delta},{lon+delta},{lat+delta}"
    try:
        r = requests.get(
            f"{OPENAQ_BASE}/locations",
            headers=OPENAQ_HEADERS,
            params={"bbox": bbox, "limit": 50},
            timeout=15,
        )
        r.raise_for_status()
        results = r.json().get("results", [])

        locations = []
        for item in results:
            coords = item.get("coordinates") or {}
            sensor_params = {}
            for s in item.get("sensors", []):
                param_name = (s.get("parameter") or {}).get("name", "").lower()
                key = PARAM_MAP.get(param_name.replace(".", ""))
                if key:
                    sensor_params[s["id"]] = key  # sensor_id → "pm25" / "pm10" / ...

            locations.append({
                "id":            item["id"],
                "name":          item.get("name", f"Station {item['id']}"),
                "lat":           float(coords.get("latitude",  lat)),
                "lon":           float(coords.get("longitude", lon)),
                "sensor_params": sensor_params,
            })

        print(f"  [OpenAQ] bbox search → найдено {len(locations)} станций")
        return locations

    except Exception as ex:
        print(f"  [OpenAQ] bbox search error: {ex}")
        return []


def _fetch_latest(location_id: int, sensor_params: dict) -> dict:
    """
    GET /v3/locations/{id}/latest
    Возвращает results[i].sensorsId + results[i].value — НЕТ parameter.name!
    Поэтому используем sensor_params маппинг полученный заранее.
    """
    data = {"pm25": 0.0, "pm10": 0.0, "no2": 0.0, "o3": 0.0}
    try:
        r = requests.get(
            f"{OPENAQ_BASE}/locations/{location_id}/latest",
            headers=OPENAQ_HEADERS,
            timeout=15,
        )
        r.raise_for_status()
        for item in r.json().get("results", []):
            sensor_id = item.get("sensorsId")
            value     = item.get("value")
            key = sensor_params.get(sensor_id)
            if key and value is not None and float(value) >= 0:
                data[key] = float(value)
    except Exception as ex:
        print(f"  [OpenAQ] latest({location_id}) error: {ex}")
    return data


def _fetch_location_info(location_id: int) -> dict | None:
    """GET /v3/locations/{id} — для hardcoded IDs когда bbox пуст."""
    try:
        r = requests.get(
            f"{OPENAQ_BASE}/locations/{location_id}",
            headers=OPENAQ_HEADERS,
            timeout=15,
        )
        r.raise_for_status()
        results = r.json().get("results", [])
        if not results:
            return None
        item   = results[0]
        coords = item.get("coordinates") or {}

        sensor_params = {}
        for s in item.get("sensors", []):
            param_name = (s.get("parameter") or {}).get("name", "").lower()
            key = PARAM_MAP.get(param_name.replace(".", ""))
            if key:
                sensor_params[s["id"]] = key

        return {
            "id":            location_id,
            "name":          item.get("name", f"Station {location_id}"),
            "lat":           float(coords.get("latitude",  config.LAT_CENTER)),
            "lon":           float(coords.get("longitude", config.LON_CENTER)),
            "sensor_params": sensor_params,
        }
    except Exception as ex:
        print(f"  [OpenAQ] info({location_id}) error: {ex}")
        return None


def fetch_air_data() -> pd.DataFrame:
    """
    Стратегия (3 уровня):
      1. bbox поиск вокруг Еревана
      2. Если пусто — hardcoded Yerevan station IDs из config.py
      3. Если данных всё равно нет — fallback значения
    """
    locations = _search_locations_bbox(config.LAT_CENTER, config.LON_CENTER)

    if not locations:
        print("  [OpenAQ] bbox пуст → hardcoded Yerevan IDs")
        for loc_id in config.YEREVAN_STATION_IDS:
            info = _fetch_location_info(loc_id)
            if info:
                locations.append(info)

    rows = []
    for loc in locations[:50]:
        m = _fetch_latest(loc["id"], loc["sensor_params"])

        if m["pm25"] == 0.0 and m["pm10"] == 0.0:
            print(f"  [OpenAQ] {loc['name'][:40]} — нет PM данных, пропускаем")
            continue

        if m["pm25"] > 500.0:
            print(f"  [OpenAQ] {loc['name'][:40]} — мусорные данные PM2.5={m['pm25']:.1f}, пропускаем")
            continue
            print(f"  [OpenAQ] {loc['name'][:40]} — нет PM данных, пропускаем")
            continue

        rows.append({"name": loc["name"], "lat": loc["lat"], "lon": loc["lon"], **m})
        print(f"  [OpenAQ] ✓ {loc['name'][:35]:37s} "
              f"PM2.5={m['pm25']:5.1f}  PM10={m['pm10']:5.1f}  "
              f"NO2={m['no2']:5.1f}  O3={m['o3']:5.1f}")
        time.sleep(0.25)

    if not rows:
        print("  [OpenAQ] ⚠ нет рабочих станций → fallback данные")
        rows = [{"name": "Yerevan (fallback)", "lat": config.LAT_CENTER, "lon": config.LON_CENTER,
                 "pm25": 20.0, "pm10": 30.0, "no2": 5.0, "o3": 60.0}]

    return pd.DataFrame(rows)


def fetch_wind_data() -> dict:
    """OWM — ветер + температура для центра Еревана."""
    try:
        r = requests.get(
            "http://api.openweathermap.org/data/2.5/weather",
            params={"lat": config.LAT_CENTER, "lon": config.LON_CENTER, "appid": config.OWM_KEY},
            timeout=10,
        ).json()
        return {
            "wind_speed": float(r.get("wind", {}).get("speed", 3.0)),
            "wind_deg":   float(r.get("wind", {}).get("deg",   270.0)),
            "temp":       float(r.get("main", {}).get("temp",  291.0)) - 273.15,
            "humidity":   float(r.get("main", {}).get("humidity", 55)),
        }
    except Exception as ex:
        print(f"  [OWM] error: {ex} → fallback")
        return {"wind_speed": 3.0, "wind_deg": 270.0, "temp": 18.0, "humidity": 55.0}