"""
predictor.py — LSTM prediction of PM2.5 for 24 hours ahead.

Architecture:
  Input:  last SEQ_LEN steps (default 24 = 24 hours)
  Features:  pm25, wind_speed, wind_sin, wind_cos, temp, humidity,
             hour_sin, hour_cos, day_of_week_sin, day_of_week_cos
  Output: pm25 after HORIZONS steps

Models are saved to models/ folder as .pt files (PyTorch).
"""

import logging
import warnings

import numpy as np
import pandas as pd
from pathlib import Path

import config
from aqi import pm25_to_aqi

warnings.filterwarnings("ignore")

logger = logging.getLogger(__name__)


def _parse_timestamps(series):
    """
    Parse timestamp column from SQLite / ISO strings. Rows may mix
    whole-second and microsecond precision (e.g. ...T22:39:56 vs ...T22:39:56.000000),
    which breaks a single inferred strptime format.
    """
    try:
        return pd.to_datetime(series, format="ISO8601", utc=False)
    except (TypeError, ValueError):
        pass
    try:
        return pd.to_datetime(series, format="mixed", utc=False)
    except TypeError:
        pass
    return pd.to_datetime(series, utc=False)


MODEL_DIR = Path(__file__).parent / "models"
MODEL_DIR.mkdir(exist_ok=True)

SEQ_LEN  = 24   # input sequence length (24 steps = 24 hours)
MIN_ROWS = 100  # minimum records for first training

HORIZONS = {
    "1h":  1,
    "3h":  3,
    "6h":  6,
    "12h": 12,
    "24h": 24,
}

FEATURE_COLS = [
    "pm25_norm", "wind_speed_norm",
    "wind_sin", "wind_cos",
    "temp_norm", "humidity_norm",
    "hour_sin", "hour_cos",
    "dow_sin", "dow_cos",
]


# ══════════════════════════════════════════════
#  Normalization
# ══════════════════════════════════════════════
class Scaler:
    """MinMax scaler for PM2.5 — saved to denormalize predictions."""
    def __init__(self):
        self.pm25_min = 0.0
        self.pm25_max = 200.0
        self.fitted   = False

    def fit(self, pm25_series):
        self.pm25_min = float(pm25_series.min())
        self.pm25_max = float(pm25_series.max()) + 1e-6
        self.fitted   = True

    def norm_pm25(self, v):
        return (v - self.pm25_min) / (self.pm25_max - self.pm25_min)

    def denorm_pm25(self, v):
        return v * (self.pm25_max - self.pm25_min) + self.pm25_min


_scaler = Scaler()


def _build_features(df_raw: pd.DataFrame, scaler: Scaler) -> pd.DataFrame:
    """Build features from raw DB data using the given PM2.5 scaler."""
    df = df_raw.copy()
    df["timestamp"] = _parse_timestamps(df["timestamp"])
    df = df.sort_values("timestamp")

    agg = df.groupby("timestamp").agg(
        pm25=("pm25",       "mean"),
        wind_speed=("wind_speed", "mean"),
        wind_deg=("wind_deg",   "mean"),
        temp=("temp",       "mean"),
        humidity=("humidity",   "mean"),
        hour=("hour",       "first"),
        day_of_week=("day_of_week", "first"),
    ).reset_index().sort_values("timestamp")

    agg["pm25_norm"]       = agg["pm25"].apply(scaler.norm_pm25)
    agg["wind_speed_norm"] = agg["wind_speed"] / 20.0
    agg["temp_norm"]       = (agg["temp"] + 30) / 70.0
    agg["humidity_norm"]   = agg["humidity"] / 100.0

    agg["wind_sin"] = np.sin(np.radians(agg["wind_deg"]))
    agg["wind_cos"] = np.cos(np.radians(agg["wind_deg"]))

    agg["hour_sin"] = np.sin(2 * np.pi * agg["hour"] / 24)
    agg["hour_cos"] = np.cos(2 * np.pi * agg["hour"] / 24)
    agg["dow_sin"]  = np.sin(2 * np.pi * agg["day_of_week"] / 7)
    agg["dow_cos"]  = np.cos(2 * np.pi * agg["day_of_week"] / 7)
    return agg.reset_index(drop=True)


def _make_sequences(features: pd.DataFrame, horizon_steps: int):
    """Slices the time series into (X, y) sequences."""
    X, y = [], []
    arr = features[FEATURE_COLS].values
    pm25_norm = features["pm25_norm"].values

    for i in range(len(arr) - SEQ_LEN - horizon_steps + 1):
        X.append(arr[i : i + SEQ_LEN])
        y.append(pm25_norm[i + SEQ_LEN + horizon_steps - 1])

    return np.array(X, dtype=np.float32), np.array(y, dtype=np.float32)


# ══════════════════════════════════════════════
#  LSTM Model (PyTorch)
# ══════════════════════════════════════════════
def _get_torch():
    try:
        import torch
        import torch.nn as nn
        return torch, nn
    except ImportError:
        return None, None


def _safe_torch_load(path: Path) -> dict:
    """Load checkpoint; prefer safe weights_only when supported."""
    torch, _ = _get_torch()
    if torch is None:
        raise ImportError("PyTorch is not installed")
    try:
        return torch.load(path, map_location="cpu", weights_only=True)
    except TypeError:
        return torch.load(path, map_location="cpu")
    except Exception:
        logger.warning("weights_only load failed for %s, retrying with full unpickle", path)
        return torch.load(path, map_location="cpu")


class LSTMModel:
    """Wrapper around PyTorch LSTM."""

    def __init__(self, input_size=len(FEATURE_COLS), hidden=64, layers=2, dropout=0.2):
        torch, nn = _get_torch()
        if torch is None:
            raise ImportError("PyTorch is not installed: pip install torch")

        class _Net(nn.Module):
            def __init__(self):
                super().__init__()
                self.lstm = nn.LSTM(
                    input_size, hidden, layers,
                    batch_first=True, dropout=dropout
                )
                self.fc = nn.Sequential(
                    nn.Linear(hidden, 32),
                    nn.ReLU(),
                    nn.Linear(32, 1),
                )

            def forward(self, x):
                out, _ = self.lstm(x)
                return self.fc(out[:, -1, :]).squeeze(-1)

        self._torch = torch
        self._nn    = nn
        self.net    = _Net()

    def train_model(self, X: np.ndarray, y: np.ndarray, epochs=100):
        torch, nn = self._torch, self._nn
        n = len(X)
        split = max(1, min(int(n * 0.85), n - 1))
        X_train, y_train = X[:split], y[:split]
        X_val, y_val = X[split:], y[split:]
        if len(X_val) == 0:
            X_val, y_val = X_train[-1:], y_train[-1:]

        X_tr = torch.tensor(X_train)
        y_tr = torch.tensor(y_train)
        X_va = torch.tensor(X_val)
        y_va = torch.tensor(y_val)

        optimizer = torch.optim.Adam(self.net.parameters(), lr=1e-3, weight_decay=1e-5)
        criterion = nn.MSELoss()
        scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=10)

        self.net.train()
        best_val = float("inf")
        best_state = None

        for epoch in range(epochs):
            self.net.train()
            optimizer.zero_grad()
            pred = self.net(X_tr)
            loss = criterion(pred, y_tr)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(self.net.parameters(), 1.0)
            optimizer.step()

            self.net.eval()
            with torch.no_grad():
                pred_v = self.net(X_va)
                val_loss = criterion(pred_v, y_va).item()
            self.net.train()
            scheduler.step(val_loss)

            if val_loss < best_val:
                best_val = val_loss
                best_state = {k: v.clone() for k, v in self.net.state_dict().items()}

        if best_state:
            self.net.load_state_dict(best_state)

        return best_val

    def predict(self, X: np.ndarray, eval_mode=True) -> np.ndarray:
        torch = self._torch
        if eval_mode:
            self.net.eval()
        with torch.no_grad():
            X_t = torch.tensor(X)
            return self.net(X_t).numpy()

    def save(self, path: Path):
        torch = self._torch
        torch.save({
            "state": self.net.state_dict(),
            "scaler_min": _scaler.pm25_min,
            "scaler_max": _scaler.pm25_max,
        }, path)

    def load(self, path: Path):
        ckpt = _safe_torch_load(path)
        self.net.load_state_dict(ckpt["state"])
        _scaler.pm25_min = ckpt["scaler_min"]
        _scaler.pm25_max = ckpt["scaler_max"]
        _scaler.fitted   = True


def _load_scaler_from_checkpoint(path: Path) -> Scaler:
    ckpt = _safe_torch_load(path)
    s = Scaler()
    s.pm25_min = float(ckpt["scaler_min"])
    s.pm25_max = float(ckpt["scaler_max"])
    s.fitted = True
    return s


def _load_model_state_only(model, path: Path) -> None:
    ckpt = _safe_torch_load(path)
    model.net.load_state_dict(ckpt["state"])


# ══════════════════════════════════════════════
#  Training
# ══════════════════════════════════════════════
def train(df_raw: pd.DataFrame):
    torch, _ = _get_torch()
    if torch is None:
        logger.warning("PyTorch is not installed: pip install torch")
        return

    if len(df_raw) < MIN_ROWS:
        logger.info("Not enough data (%s rows, need ≥%s)", len(df_raw), MIN_ROWS)
        return

    logger.info("Building features from %s records...", len(df_raw))
    _scaler.fit(df_raw["pm25"])

    features = _build_features(df_raw, _scaler)

    if len(features) < SEQ_LEN + 20:
        logger.info("Not enough time steps (%s)", len(features))
        return

    trained = 0
    for name, steps in HORIZONS.items():
        X, y = _make_sequences(features, steps)
        if len(X) < 10:
            continue

        logger.info("Training model %s (%s examples)...", name, len(X))
        model = LSTMModel()
        loss  = model.train_model(X, y, epochs=150)
        model.save(MODEL_DIR / f"lstm_{name}.pt")
        logger.info("%s val_loss=%.4f ✓", name, loss)
        trained += 1

    logger.info("Done — %s models saved", trained)


# ══════════════════════════════════════════════
#  Prediction
# ══════════════════════════════════════════════
def predict(df_raw: pd.DataFrame, wind: dict) -> list[dict]:
    _ = wind  # reserved for future conditioning on forecast weather
    torch, _ = _get_torch()
    results = []
    has_torch = torch is not None
    mc_n = getattr(config, "LSTM_MC_SAMPLES", 12)

    for name, steps in HORIZONS.items():
        model_path = MODEL_DIR / f"lstm_{name}.pt"
        used_model = "physics"
        confidence = 0.25

        if has_torch and model_path.exists() and len(df_raw) >= SEQ_LEN:
            try:
                scaler = _load_scaler_from_checkpoint(model_path)
                features = _build_features(df_raw, scaler)
                if features is None or len(features) < SEQ_LEN:
                    raise ValueError("insufficient feature rows")

                model = LSTMModel()
                _load_model_state_only(model, model_path)

                seq = features[FEATURE_COLS].values[-SEQ_LEN:]
                X   = seq[np.newaxis].astype(np.float32)

                model.net.train()
                preds = []
                for _ in range(mc_n):
                    p = float(model.predict(X, eval_mode=False)[0])
                    preds.append(scaler.denorm_pm25(p))

                pred_pm25  = float(np.mean(preds))
                pred_std   = float(np.std(preds))
                confidence = min(0.95, max(0.3, 1.0 - pred_std / (pred_pm25 + 1e-6)))
                used_model = "lstm"

            except Exception as ex:
                logger.warning("predict(%s) error: %s", name, ex)
                pred_pm25 = float(df_raw["pm25"].mean() * (0.97 ** steps))
                pred_std  = pred_pm25 * 0.15
        else:
            current = float(df_raw["pm25"].mean()) if len(df_raw) > 0 else 20.0
            BACKGROUND_PM25 = 8.0
            pred_pm25 = max(BACKGROUND_PM25, current * (0.995 ** steps))
            pred_std  = pred_pm25 * 0.2

        pred_pm25 = max(0.0, pred_pm25)
        pred_std  = max(0.0, pred_std)

        aqi, label, color = pm25_to_aqi(pred_pm25)
        aqi_lo, _, _      = pm25_to_aqi(max(0, pred_pm25 - pred_std))
        aqi_hi, _, _      = pm25_to_aqi(pred_pm25 + pred_std)

        results.append({
            "horizon":    name,
            "minutes":    steps * 60,
            "hours":      round(float(steps), 1),
            "pm25":       round(pred_pm25, 1),
            "pm25_lo":    round(max(0, pred_pm25 - pred_std), 1),
            "pm25_hi":    round(pred_pm25 + pred_std, 1),
            "aqi":        aqi,
            "aqi_lo":     aqi_lo,
            "aqi_hi":     aqi_hi,
            "label":      label,
            "color":      color,
            "confidence": round(confidence, 2),
            "model":      used_model,
        })

    return results


# ══════════════════════════════════════════════
#  Сравнение prediction vs reality
# ══════════════════════════════════════════════
def _rotate_predictions_log_if_needed():
    eval_path = MODEL_DIR / "predictions_log.jsonl"
    max_b = getattr(config, "PREDICTIONS_LOG_MAX_BYTES", 5 * 1024 * 1024)
    if not eval_path.exists():
        return
    try:
        if eval_path.stat().st_size <= max_b:
            return
        rotated = eval_path.with_suffix(".jsonl.bak")
        if rotated.exists():
            rotated.unlink()
        eval_path.rename(rotated)
        logger.info("Rotated predictions log (size exceeded %s bytes)", max_b)
    except OSError as e:
        logger.warning("Could not rotate predictions log: %s", e)


def save_prediction_for_eval(prediction: list, timestamp: str):
    """Saves predictions to compare with reality later."""
    import json
    _rotate_predictions_log_if_needed()
    eval_path = MODEL_DIR / "predictions_log.jsonl"
    with open(eval_path, "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": timestamp, "predictions": prediction}) + "\n")


def get_prediction_vs_reality(df_raw: pd.DataFrame) -> list[dict]:
    """
    Compares past predictions with actual data (24h horizon).
    Returns list of points for the chart.
    """
    import json
    eval_path = MODEL_DIR / "predictions_log.jsonl"
    if not eval_path.exists():
        return []

    results = []
    df_raw = df_raw.copy()
    df_raw["timestamp"] = _parse_timestamps(df_raw["timestamp"])

    try:
        with open(eval_path, encoding="utf-8") as f:
            lines = f.readlines()[-200:]

        for line in lines:
            entry = json.loads(line)
            ts    = _parse_timestamps(pd.Series([entry["ts"]])).iloc[0]

            pred_24h = next((p for p in entry["predictions"] if p["horizon"] == "24h"), None)
            if not pred_24h:
                continue

            target_ts = ts + pd.Timedelta(hours=24)
            real_rows = df_raw[
                (df_raw["timestamp"] >= target_ts - pd.Timedelta(hours=1)) &
                (df_raw["timestamp"] <= target_ts + pd.Timedelta(hours=1))
            ]

            if real_rows.empty:
                continue

            real_pm25 = float(real_rows["pm25"].mean())
            results.append({
                "ts":          ts.strftime("%Y-%m-%d"),
                "pred_pm25":   pred_24h["pm25"],
                "real_pm25":   round(real_pm25, 1),
                "pred_aqi":    pred_24h["aqi"],
                "real_aqi":    pm25_to_aqi(real_pm25)[0],
                "error":       round(abs(pred_24h["pm25"] - real_pm25), 1),
            })
    except Exception as ex:
        logger.warning("eval error: %s", ex)

    return results[-24:]
