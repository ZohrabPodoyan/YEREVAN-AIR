# 🌆 Yerevan Air: Real-Time Monitoring & Predictive System (v4.0)

A professional-grade environmental intelligence platform for Yerevan, Armenia. This system combines real-time IoT data ingestion, physics-based dispersion modeling, and LSTM deep learning to provide accurate air quality insights and forecasts.

[![Yerevan Air CI](https://github.com/ZohrabPodoyan/yerevan_air/actions/workflows/python-app.yml/badge.svg)](https://github.com/ZohrabPodoyan/yerevan_air/actions)
**Live Demo:** [yerevan-air-production.up.railway.app](https://yerevan-air-production.up.railway.app)

## Features

### 🛰 Data & Visualization
- **Real-Time Ingestion**: Fetches PM2.5, PM10, NO2, and O3 from **OpenAQ v3** (45+ stations) every 5 minutes.
- **Physics Engine**: Wind-driven particle dispersion simulation using **Perlin noise** (OpenSimplex) for turbulence and terrain-aware stagnation factors.
- **Satellite Overlay**: NASA GIBS MODIS Terra/Aqua Aerosol Optical Depth integration.
- **Interactive Dashboard**: Leaflet-based map with district-level GeoJSON boundaries and dynamic heatmaps.

### 🧠 Machine Learning & Analytics
- **LSTM Forecasting**: PyTorch-based Long Short-Term Memory models predicting PM2.5 for 1h, 3h, 6h, 12h, and 24h horizons.
- **Anomaly Detection**: Automatic detection of PM2.5 spikes with wind-vector analysis to identify probable pollution sources.
- **Correlation Analysis**: Statistical breakdowns of air quality by hour of the day and day of the week.
- **District Ranking**: Real-time leaderboard of Yerevan's 12 administrative districts.

### 🤖 Integration & Monitoring
- **Telegram Bot**: Automated alerts on AQI threshold breaches, daily morning digests, and on-demand status reports via `@YerevanAirBot`.
- **Server Health**: Integrated monitoring of CPU, RAM, and Disk usage with automated alerts via `psutil`.
- **E2E Testing**: Robust testing suite using **Playwright** for UI verification and **Pytest** for core logic.

## Data Sources
- **Air quality**: OpenAQ v3 — real monitoring stations.
- **Wind/Weather**: OpenWeatherMap (OWM).
- **Satellite**: NASA GIBS (Global Imagery Browse Services).

## Tech Stack
- **Backend**: Python 3.10, Flask (Web Server), SQLite (Time-series data).
- **Deep Learning**: PyTorch (LSTM).
- **Frontend**: Jinja2, Leaflet.js, OpenSimplex.
- **DevOps**: GitHub Actions (CI), Railway.app (PaaS), Nixpacks.

## Installation & Setup

### 1. Clone
```bash
git clone https://github.com/ZohrabPodoyan/yerevan-air
cd yerevan-air
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
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
-yerevan_air/ -
├── .github/workflows/ # CI/CD pipelines (GitHub Actions) +
├── models/ # Saved PyTorch LSTM checkpoints (.pt files) +
├── templates/ # Jinja2 dashboard templates (base.html, districts.js) +
├── tests/ # Playwright E2E and Pytest unit tests +
├── server.py # Flask web server entry point +
├── main.py # CLI simulation loop +
├── core.py # Orchestration logic for data cycles +
├── config.py # API keys & simulation parameters +
├── fetcher.py # Data ingestion (OpenAQ v3 & OWM) +
├── aqi.py # US EPA AQI conversion & Beaufort scale +
├── physics.py # Wind dispersion & Perlin noise logic +
├── predictor.py # LSTM architecture & training logic +
├── forecast.py # Visual dispersion lookahead simulation +
├── database.py # SQLite persistence layer +
├── renderer.py # HTML generation & data serialization +
├── telegram_bot.py # Alerts, digests, and command handling +
├── anomaly.py # Spike detection & pollution source analysis +
├── server_monitor.py # Resource tracking (CPU/RAM/Disk) +
├── district_ranking.py # Geographic performance metrics +
├── correlation.py # Time-series statistical analysis +
├── weather_forecast.py # 3-day weather integration +
├── requirements.txt # Python dependencies +
└── railway.json # Cloud deployment configuration
```

## LSTM Model
The prediction model improves over time:
- **0-3h**: Physics fallback (decay model), confidence ~25%
- **3-17h** (200+ records): First LSTM training
- **2 days** (500+ records): Confidence 60-70%
- **1 week** (1000+ records): MAE < 5 μg/m³
