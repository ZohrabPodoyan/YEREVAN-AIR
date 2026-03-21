"""
predictor.py — LSTM предсказание PM2.5 на 24 часа вперёд.

Архитектура:
  Вход:  последние SEQ_LEN шагов (по умолчанию 24 = 2 часа)
  Фичи:  pm25, wind_speed, wind_sin, wind_cos, temp, humidity,
         hour_sin, hour_cos, day_of_week_sin, day_of_week_cos
  Выход: pm25 через HORIZONS шагов

Модели сохраняются в папку models/ как .pt файлы (PyTorch).
"""

import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime
import warnings
warnings.filterwarnings("ignore")

MODEL_DIR = Path(__file__).parent / "models"
MODEL_DIR.mkdir(exist_ok=True)

SEQ_LEN  = 24   # длина входной последовательности (24 шага = 2 часа)
MIN_ROWS = 100  # минимум записей для первого обучения

HORIZONS = {
    "1h":  12,
    "3h":  36,
    "6h":  72,
    "12h": 144,
    "24h": 288,
}

FEATURE_COLS = [
    "pm25_norm", "wind_speed_norm",
    "wind_sin", "wind_cos",
    "temp_norm", "humidity_norm",
    "hour_sin", "hour_cos",
    "dow_sin", "dow_cos",
]


# ══════════════════════════════════════════════
#  Нормализация
# ══════════════════════════════════════════════
class Scaler:
    """MinMax scaler для PM2.5 — сохраняем чтобы денормализовать предсказания."""
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


def _build_features(df_raw: pd.DataFrame) -> pd.DataFrame:
    """Строит фичи из сырых данных БД."""
    df = df_raw.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp")

    # Усредняем по всем станциям за каждый шаг
    agg = df.groupby("timestamp").agg(
        pm25=("pm25",       "mean"),
        wind_speed=("wind_speed", "mean"),
        wind_deg=("wind_deg",   "mean"),
        temp=("temp",       "mean"),
        humidity=("humidity",   "mean"),
        hour=("hour",       "first"),
        day_of_week=("day_of_week", "first"),
    ).reset_index().sort_values("timestamp")

    _scaler.fit(agg["pm25"])

    agg["pm25_norm"]       = agg["pm25"].apply(_scaler.norm_pm25)
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
    """Нарезает временной ряд на (X, y) последовательности."""
    X, y = [], []
    arr = features[FEATURE_COLS].values
    pm25_norm = features["pm25_norm"].values

    for i in range(len(arr) - SEQ_LEN - horizon_steps):
        X.append(arr[i : i + SEQ_LEN])
        y.append(pm25_norm[i + SEQ_LEN + horizon_steps - 1])

    return np.array(X, dtype=np.float32), np.array(y, dtype=np.float32)


# ══════════════════════════════════════════════
#  LSTM модель (PyTorch)
# ══════════════════════════════════════════════
def _get_torch():
    try:
        import torch
        import torch.nn as nn
        return torch, nn
    except ImportError:
        return None, None


class LSTMModel:
    """Обёртка над PyTorch LSTM."""

    def __init__(self, input_size=len(FEATURE_COLS), hidden=64, layers=2, dropout=0.2):
        torch, nn = _get_torch()
        if torch is None:
            raise ImportError("PyTorch не установлен: pip install torch")

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
        X_t = torch.tensor(X)
        y_t = torch.tensor(y)

        optimizer = torch.optim.Adam(self.net.parameters(), lr=1e-3, weight_decay=1e-5)
        criterion = nn.MSELoss()
        scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=10)

        self.net.train()
        best_loss = float("inf")
        best_state = None

        for epoch in range(epochs):
            optimizer.zero_grad()
            pred = self.net(X_t)
            loss = criterion(pred, y_t)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(self.net.parameters(), 1.0)
            optimizer.step()
            scheduler.step(loss)

            if loss.item() < best_loss:
                best_loss = loss.item()
                best_state = {k: v.clone() for k, v in self.net.state_dict().items()}

        if best_state:
            self.net.load_state_dict(best_state)

        return best_loss

    def predict(self, X: np.ndarray) -> np.ndarray:
        torch = self._torch
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
        torch = self._torch
        ckpt = torch.load(path, map_location="cpu")
        self.net.load_state_dict(ckpt["state"])
        _scaler.pm25_min = ckpt["scaler_min"]
        _scaler.pm25_max = ckpt["scaler_max"]
        _scaler.fitted   = True


# ══════════════════════════════════════════════
#  Обучение
# ══════════════════════════════════════════════
def train(df_raw: pd.DataFrame):
    torch, _ = _get_torch()
    if torch is None:
        print("  [LSTM] PyTorch не установлен: pip install torch")
        return

    if len(df_raw) < MIN_ROWS:
        print(f"  [LSTM] Мало данных ({len(df_raw)} строк, нужно ≥{MIN_ROWS})")
        return

    print(f"  [LSTM] Строим фичи из {len(df_raw)} записей...")
    features = _build_features(df_raw)

    if len(features) < SEQ_LEN + 20:
        print(f"  [LSTM] Недостаточно временных шагов ({len(features)})")
        return

    trained = 0
    for name, steps in HORIZONS.items():
        X, y = _make_sequences(features, steps)
        if len(X) < 10:
            continue

        print(f"  [LSTM] Обучаю модель {name} ({len(X)} примеров)...")
        model = LSTMModel()
        loss  = model.train_model(X, y, epochs=150)
        model.save(MODEL_DIR / f"lstm_{name}.pt")
        print(f"  [LSTM] {name} loss={loss:.4f} ✓")
        trained += 1

    print(f"  [LSTM] Готово — {trained} моделей сохранено")


# ══════════════════════════════════════════════
#  Предсказание
# ══════════════════════════════════════════════
def predict(df_raw: pd.DataFrame, wind: dict) -> list[dict]:
    from aqi import pm25_to_aqi
    torch, _ = _get_torch()

    results   = []
    has_torch = torch is not None
    features  = _build_features(df_raw) if len(df_raw) >= SEQ_LEN else None

    for name, steps in HORIZONS.items():
        model_path = MODEL_DIR / f"lstm_{name}.pt"
        used_model = "physics"
        confidence = 0.25

        if has_torch and model_path.exists() and features is not None and len(features) >= SEQ_LEN:
            try:
                model = LSTMModel()
                model.load(model_path)

                # Последовательность для предсказания
                seq = features[FEATURE_COLS].values[-SEQ_LEN:]
                X   = seq[np.newaxis].astype(np.float32)

                # Monte Carlo dropout для confidence interval
                import torch.nn as nn
                model.net.train()  # включаем dropout для MC sampling
                preds = []
                for _ in range(30):
                    p = float(model.predict(X)[0])
                    preds.append(_scaler.denorm_pm25(p))

                pred_pm25  = float(np.mean(preds))
                pred_std   = float(np.std(preds))
                confidence = min(0.95, max(0.3, 1.0 - pred_std / (pred_pm25 + 1e-6)))
                used_model = "lstm"

            except Exception as ex:
                print(f"  [LSTM] predict({name}) error: {ex}")
                pred_pm25 = float(df_raw["pm25"].mean() * (0.97 ** steps))
                pred_std  = pred_pm25 * 0.15
        else:
            # Физическая модель затухания как fallback
            current = float(df_raw["pm25"].mean()) if len(df_raw) > 0 else 20.0
            BACKGROUND_PM25 = 8.0   # фоновый уровень μg/m³ для Еревана
            pred_pm25 = max(BACKGROUND_PM25, current * (0.995 ** steps))
            pred_std  = pred_pm25 * 0.2

        pred_pm25 = max(0.0, pred_pm25)
        pred_std  = max(0.0, pred_std)

        aqi, label, color = pm25_to_aqi(pred_pm25)
        aqi_lo, _, _      = pm25_to_aqi(max(0, pred_pm25 - pred_std))
        aqi_hi, _, _      = pm25_to_aqi(pred_pm25 + pred_std)

        results.append({
            "horizon":    name,
            "minutes":    steps * 5,
            "hours":      round(steps * 5 / 60, 1),
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
def save_prediction_for_eval(prediction: list, timestamp: str):
    """Сохраняем предсказания чтобы потом сравнить с реальностью."""
    import json
    eval_path = MODEL_DIR / "predictions_log.jsonl"
    with open(eval_path, "a") as f:
        f.write(json.dumps({"ts": timestamp, "predictions": prediction}) + "\n")


def get_prediction_vs_reality(df_raw: pd.DataFrame) -> list[dict]:
    """
    Сравнивает прошлые предсказания с реальными данными.
    Возвращает список точек для графика.
    """
    import json
    eval_path = MODEL_DIR / "predictions_log.jsonl"
    if not eval_path.exists():
        return []

    results = []
    df_raw["timestamp"] = pd.to_datetime(df_raw["timestamp"])

    try:
        with open(eval_path) as f:
            lines = f.readlines()[-50:]  # последние 50 предсказаний

        for line in lines:
            entry = json.loads(line)
            ts    = pd.to_datetime(entry["ts"])

            # Для горизонта 1h ищем реальное значение через 1h после предсказания
            pred_1h = next((p for p in entry["predictions"] if p["horizon"] == "1h"), None)
            if not pred_1h:
                continue

            target_ts = ts + pd.Timedelta(hours=1)
            real_rows = df_raw[
                (df_raw["timestamp"] >= target_ts - pd.Timedelta(minutes=10)) &
                (df_raw["timestamp"] <= target_ts + pd.Timedelta(minutes=10))
            ]

            if real_rows.empty:
                continue

            real_pm25 = float(real_rows["pm25"].mean())
            results.append({
                "ts":          ts.strftime("%H:%M"),
                "pred_pm25":   pred_1h["pm25"],
                "real_pm25":   round(real_pm25, 1),
                "pred_aqi":    pred_1h["aqi"],
                "real_aqi":    pm25_to_aqi(real_pm25)[0],
                "error":       round(abs(pred_1h["pm25"] - real_pm25), 1),
            })
    except Exception as ex:
        print(f"  [LSTM] eval error: {ex}")

    return results[-24:]  # последние 24 точки


def pm25_to_aqi(pm25):
    from aqi import pm25_to_aqi as _fn
    return _fn(pm25)