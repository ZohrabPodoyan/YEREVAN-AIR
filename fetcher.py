"""
fetcher.py — Fetch data from two sources:
  • OpenAQ v3   → PM2.5, PM10, NO2, O3  (real stations)
  • OWM         → wind speed/direction, temperature, humidity

Bugs fixed:
  - coordinates + radius returned 422 (order_by=distance incompatible) → use bbox
  - /latest doesn't contain parameter.name → get sensor_id mapping from /locations/{id}
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


def _search_locations_bbox(session: requests.Session, lat: float, lon: float, delta: float = 0.3) -> list[dict]:
    """
    GET /v3/locations?bbox=minLon,minLat,maxLon,maxLat
    delta=0.3° ≈ 33 km — covers all Yerevan.
    Build sensor_id → parameter mapping from sensors[].
    """
    bbox = f"{lon-delta},{lat-delta},{lon+delta},{lat+delta}"
    try:
        r = session.get(
            f"{OPENAQ_BASE}/locations",
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

        print(f"  [OpenAQ] bbox search → found {len(locations)} stations")
        return locations

    except Exception as ex:
        print(f"  [OpenAQ] bbox search error: {ex}")
        return []


def _fetch_latest(session: requests.Session, location_id: int, sensor_params: dict) -> dict:
    """
    GET /v3/locations/{id}/latest
    Returns results[i].sensorsId + results[i].value — NO parameter.name!
    Therefore use sensor_params mapping obtained earlier.
    """
    data = {"pm25": 0.0, "pm10": 0.0, "no2": 0.0, "o3": 0.0}
    try:
        r = session.get(
            f"{OPENAQ_BASE}/locations/{location_id}/latest",
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


def _fetch_location_info(session: requests.Session, location_id: int) -> dict | None:
    """GET /v3/locations/{id} — for hardcoded IDs when bbox is empty."""
    try:
        r = session.get(
            f"{OPENAQ_BASE}/locations/{location_id}",
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
    session = requests.Session()
    session.headers.update(OPENAQ_HEADERS)

    locations = _search_locations_bbox(session, config.LAT_CENTER, config.LON_CENTER)

    if not locations:
        print("  [OpenAQ] bbox empty → hardcoded Yerevan IDs")
        for loc_id in config.YEREVAN_STATION_IDS:
            info = _fetch_location_info(session, loc_id)
            if info:
                locations.append(info)

    rows = []
    seen_names = set()

    for loc in locations[:50]:
        m = _fetch_latest(session, loc["id"], loc["sensor_params"]) 

        if m["pm25"] == 0.0 and m["pm10"] == 0.0:
            print(f"  [OpenAQ] {loc['name'][:40]} — no PM data, skipping")
            continue

        if m["pm25"] > 500.0:
            print(f"  [OpenAQ] {loc['name'][:40]} — invalid data PM2.5={m['pm25']:.1f}, skipping")
            continue

        base_name = loc["name"][:40]
        if base_name in seen_names:
            print(f"  [OpenAQ] {loc['name'][:40]} — duplicate, skipping")
            continue
        seen_names.add(base_name)

        rows.append({"name": loc["name"], "lat": loc["lat"], "lon": loc["lon"], **m})
        print(f"  [OpenAQ] ✓ {loc['name'][:35]:37s} "
              f"PM2.5={m['pm25']:5.1f}  PM10={m['pm10']:5.1f}")
        time.sleep(1.0)

    if not rows:
        print("  [OpenAQ] ⚠ no working stations → fallback data")
        rows = [{"name": "Yerevan (fallback)", "lat": config.LAT_CENTER, "lon": config.LON_CENTER,
                 "pm25": 20.0, "pm10": 30.0, "no2": 5.0, "o3": 60.0}]

    return pd.DataFrame(rows)


def fetch_wind_data() -> dict:
    """OWM — wind + temperature for Yerevan center."""
    session = requests.Session()
    try:
        r = session.get(
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