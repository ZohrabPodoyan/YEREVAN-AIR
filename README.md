# 🌆 Yerevan Air Pollution Simulation

Real-time air quality monitoring and pollution dispersion simulation for Yerevan, Armenia.

## Features
- 🗺 Live heatmap from OpenAQ v3 monitoring stations
- 🌬 Wind-driven particle dispersion simulation
- 🛰 NASA GIBS satellite PM2.5 overlay
- 📊 US EPA AQI index with color coding
- 🔮 LSTM ML prediction (24h forecast)
- ⚠ Alerts when AQI exceeds threshold
- 📈 History chart + prediction vs reality

## Data Sources
- **Air quality**: [OpenAQ v3](https://openaq.org) — free, real monitoring stations
- **Wind/Weather**: [OpenWeatherMap](https://openweathermap.org)
- **Satellite**: NASA GIBS MODIS Terra Aerosol

## Setup

### 1. Clone
```bash
git clone https://github.com/YOUR_USERNAME/yerevan-air
cd yerevan-air
```

### 2. Install dependencies
```bash
pip install pandas numpy requests joblib torch
```

### 3. Configure API keys
```bash
cp config.example.py config.py
# Edit config.py and add your API keys
```

Get free keys:
- OpenAQ: https://explore.openaq.org/register
- OpenWeatherMap: https://openweathermap.org/api

### 4. Run
```bash
python main.py
# Open yerevan_air.html in browser
```

## Project Structure
```
yerevan_air/
├── main.py          # Main simulation loop
├── config.py        # API keys and settings (not in repo)
├── config.example.py
├── fetcher.py       # OpenAQ v3 + OWM data fetching
├── aqi.py           # US EPA AQI conversion
├── physics.py       # Wind dispersion physics
├── history.py       # AQI history tracking
├── alerts.py        # Threshold alerts
├── forecast.py      # 1-hour dispersion forecast
├── predictor.py     # LSTM ML prediction model
├── database.py      # SQLite data collection
├── renderer.py      # HTML dashboard generator
└── template.html    # Dashboard template
```

## LSTM Model
The prediction model improves over time:
- **0-3h**: Physics fallback (decay model), confidence ~25%
- **3-17h** (200+ records): First LSTM training
- **2 days** (500+ records): Confidence 60-70%
- **1 week** (1000+ records): MAE < 5 μg/m³

## Screenshot
![Dashboard](screenshot.png)