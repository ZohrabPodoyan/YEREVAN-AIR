"""
core.py - Common simulation logic for main.py and server.py
"""
from fetcher import fetch_air_data, fetch_wind_data
from physics import wind_displacement, step_particles, emit_particles, trim_particles
from renderer import render
from alerts import check_alerts
from database import save_measurements, get_training_data, get_row_count
from predictor import train, predict, save_prediction_for_eval, get_prediction_vs_reality
from correlation import get_correlation_data
from district_ranking import get_district_ranking
from weather_forecast import fetch_openwm_forecast, get_weather_forecast, get_hourly_wind_series
from anomaly import detect_anomalies
from server_monitor import check_server_alerts
from datetime import datetime

import config

_cycle_num = 0
_last_correlation = None
_last_ranking = None


def run_cycle(particles: list) -> tuple[list, str]:
    """
    One simulation cycle.
    Returns (new particles, html string)
    """
    global _cycle_num, _last_correlation, _last_ranking

    df = fetch_air_data()
    wind = fetch_wind_data()

    save_measurements(df, wind)
    row_count = get_row_count()

    df_train = get_training_data()

    # Train every 1000 rows (cadence depends on station rows per cycle)
    if row_count % 1000 == 0 and row_count > 0:
        train(df_train)

    prediction = predict(df_train, wind)
    save_prediction_for_eval(prediction, datetime.now().replace(microsecond=0).isoformat())
    vs_reality = get_prediction_vs_reality(df_train)

    new_alerts      = check_alerts(df)
    server_alerts   = check_server_alerts()
    all_alerts      = new_alerts + server_alerts
    owm_fc = fetch_openwm_forecast(40)

    d_lat, d_lon = wind_displacement(wind["wind_speed"], wind["wind_deg"], config.DT)
    particles    = step_particles(particles, d_lat, d_lon)
    particles   += emit_particles(df)
    particles    = trim_particles(particles)

    _cycle_num += 1
    every = getattr(config, "ANALYTICS_EVERY_N_CYCLES", 1)
    if _cycle_num % every == 0:
        _last_correlation = get_correlation_data()
        _last_ranking = get_district_ranking()
    if _last_correlation is None:
        _last_correlation = get_correlation_data()
        _last_ranking = get_district_ranking()

    correlation = _last_correlation
    ranking = _last_ranking

    weather_forecast = get_weather_forecast(owm_fc)
    anomalies        = detect_anomalies(df, wind)

    html = render(
        particles, df, wind,
        all_alerts,
        prediction, vs_reality,
        correlation, ranking,
        weather_forecast, anomalies
    )

    from telegram_bot import notify_alerts, set_latest_df, set_latest_wind
    set_latest_df(df)
    set_latest_wind(wind)
    if new_alerts:
        notify_alerts(new_alerts)

    return particles, html
