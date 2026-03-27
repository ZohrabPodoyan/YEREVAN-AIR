"""Smoke tests for DB, renderer, and predictor fallbacks."""
import importlib


def test_database_init_and_connect(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    import database
    importlib.reload(database)
    database.init_db()
    with database.connect_db() as conn:
        n = conn.execute("SELECT COUNT(*) FROM measurements").fetchone()[0]
        assert n == 0


def test_renderer_includes_station_cards():
    import pandas as pd
    from renderer import render

    df = pd.DataFrame([{
        "name": "Test Station",
        "lat": 40.18,
        "lon": 44.51,
        "pm25": 35.0,
        "pm10": 45.0,
        "no2": 12.0,
        "o3": 55.0,
    }])
    wind = {"wind_speed": 3.0, "wind_deg": 270.0, "temp": 18.0, "humidity": 55.0}
    html = render([], df, wind)
    assert "dist-card" in html
    assert "mini-bar-row" in html
    assert "ticker-item" in html


def test_predict_physics_fallback_without_models(monkeypatch, tmp_path):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "t.db"))
    import database
    import predictor
    importlib.reload(database)
    importlib.reload(predictor)
    predictor.MODEL_DIR = tmp_path / "models"
    predictor.MODEL_DIR.mkdir(exist_ok=True)

    import pandas as pd
    df = pd.DataFrame({
        "timestamp": pd.date_range("2024-01-01", periods=30, freq="h"),
        "station": ["s"] * 30,
        "pm25": [20.0] * 30,
        "wind_speed": [3.0] * 30,
        "wind_deg": [270.0] * 30,
        "temp": [18.0] * 30,
        "humidity": [55.0] * 30,
        "hour": list(range(30)),
        "day_of_week": [0] * 30,
        "month": [1] * 30,
    })
    out = predictor.predict(df, {"wind_speed": 3.0})
    assert len(out) == 5
    assert all(h["model"] == "physics" for h in out)


def test_safe_torch_load_missing_file(tmp_path):
    from predictor import _safe_torch_load
    import pytest
    p = tmp_path / "none.pt"
    with pytest.raises((FileNotFoundError, OSError)):
        _safe_torch_load(p)
