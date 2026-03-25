"""
core.py - Common simulation logic for main.py and server.py
"""
from fetcher import fetch_air_data, fetch_wind_data
from physics import wind_displacement, step_particles, emit_particles, trim_particles
from renderer import render
from alerts import check_alerts
from forecast import run_forecast
from database import init_db, save_measurements, get_training_data, get_row_count
from predictor import train, predict, save_prediction_for_eval, get_prediction_vs_reality
from correlation import get_correlation_data
from district_ranking import get_district_ranking
from weather_forecast import get_weather_forecast
from anomaly import detect_anomalies
from server_monitor import check_server_alerts
from datetime import datetime


def run_cycle(particles: list) -> tuple[list, str]:
    """
    One simulation cycle.
    Returns (new particles, html string)
    """
    import config

    df   = fetch_air_data()
    wind = fetch_wind_data()

    save_measurements(df, wind)
    row_count = get_row_count()

    if row_count % 100 == 0 and row_count > 0:
        train(get_training_data())

    prediction  = predict(get_training_data(), wind)
    save_prediction_for_eval(prediction, datetime.now().isoformat())
    vs_reality  = get_prediction_vs_reality(get_training_data())

    new_alerts      = check_alerts(df)
    server_alerts   = check_server_alerts()
    all_alerts      = new_alerts + server_alerts
    forecast_frames = run_forecast(particles, df, wind)

    d_lat, d_lon = wind_displacement(wind["wind_speed"], wind["wind_deg"], config.DT)
    particles    = step_particles(particles, d_lat, d_lon)
    particles   += emit_particles(df)
    particles    = trim_particles(particles)

    correlation      = get_correlation_data()
    ranking          = get_district_ranking()
    weather_forecast = get_weather_forecast()
    anomalies        = detect_anomalies(df, wind)

    html = render(
        particles, df, wind,
        all_alerts, forecast_frames,
        prediction, vs_reality,
        correlation, ranking,
        weather_forecast, anomalies
    )

    # Telegram notifications
    from telegram_bot import notify_alerts, set_latest_df, set_latest_wind
    set_latest_df(df)
    set_latest_wind(wind)
    if new_alerts:
        notify_alerts(new_alerts)

    return particles, html