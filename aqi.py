# ══════════════════════════════════════════════
#  AQI — US EPA стандарт
#  PM2.5 (μg/m³)  →  AQI (0–500)
# ══════════════════════════════════════════════

AQI_BREAKPOINTS = [
    # (C_low, C_high, AQI_low, AQI_high, label, hex_color)
    (0.0,    12.0,    0,   50,  "Good",               "#00e676"),
    (12.1,   35.4,   51,  100,  "Moderate",           "#ffee58"),
    (35.5,   55.4,  101,  150,  "Unhealthy for Some", "#ffa726"),
    (55.5,  150.4,  151,  200,  "Unhealthy",          "#ef5350"),
    (150.5, 250.4,  201,  300,  "Very Unhealthy",     "#ab47bc"),
    (250.5, 500.4,  301,  500,  "Hazardous",          "#270000"),
]


def pm25_to_aqi(pm25: float) -> tuple:
    pm25 = max(0.0, float(pm25))
    for c_lo, c_hi, a_lo, a_hi, label, color in AQI_BREAKPOINTS:
        if pm25 <= c_hi:
            aqi = (a_hi - a_lo) / (c_hi - c_lo) * (pm25 - c_lo) + a_lo
            return int(round(aqi)), label, color
    return 500, "Hazardous", "#270000"


def beaufort_scale(speed_ms: float) -> int:
    """Скорость ветра (м/с) → число Бофорта."""
    thresholds = [0.3, 1.6, 3.4, 5.5, 8.0, 10.8, 13.9, 17.2, 20.8, 24.5, 28.5, 32.7]
    for i, v in enumerate(thresholds):
        if speed_ms < v:
            return i
    return 12
