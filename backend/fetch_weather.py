"""Hourly weather for the 8 stations from Open-Meteo (no key needed).

Two kinds of data, saved to data/live/:
  weather_hist_<id>.csv  - archived *forecasts* (Historical Forecast API), used for training, so that
                           training weather is the same kind of product the live system receives.
  weather_fcst_<id>.csv  - the current forecast for the next days (Forecast API), used live.

Usage (project root, aqi env):
    python backend/fetch_weather.py --start 2025-02-19 --end 2026-10-14
    python backend/fetch_weather.py --forecast-only
"""
import argparse
import datetime as dt
import time
from pathlib import Path

import pandas as pd
import requests

STATIONS = {6975: (12.917348, 77.622813), 6984: (13.029152, 77.585901), 6973: (12.920984, 77.584908),
            6954: (13.428828, 77.731418), 10902: (13.328028, 75.797056), 7289: (12.21041, 76.37376),
            10909: (12.733409, 77.298051), 11582: (12.415911, 75.73505)}
VARS = "temperature_2m,relative_humidity_2m,wind_speed_10m,wind_direction_10m"
OUT = Path(__file__).resolve().parents[1] / "data" / "live"
HIST_URL = "https://historical-forecast-api.open-meteo.com/v1/forecast"
FCST_URL = "https://api.open-meteo.com/v1/forecast"


def get(url, lat, lon, **extra):
    params = dict(latitude=lat, longitude=lon, hourly=VARS, wind_speed_unit="ms",
                  timezone="Asia/Kolkata", **extra)
    for attempt in range(5):  # Open-Meteo sometimes resets connections; retry with a growing pause
        try:
            r = requests.get(url, params=params, timeout=120)
            r.raise_for_status()
            break
        except requests.RequestException:
            if attempt == 4:
                raise
            time.sleep(5 * (attempt + 1))
    h = r.json()["hourly"]
    df = pd.DataFrame(h).rename(columns={"time": "datetimeLocal"})
    df["datetimeLocal"] = pd.to_datetime(df["datetimeLocal"]).dt.tz_localize("Asia/Kolkata")
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=dt.date.fromisoformat, default=dt.date(2025, 2, 19))
    ap.add_argument("--end", type=dt.date.fromisoformat, default=dt.date.today())
    ap.add_argument("--forecast-only", action="store_true")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    for lid, (lat, lon) in STATIONS.items():
        msg = f"{lid}:"
        if not a.forecast_only:
            hist = get(HIST_URL, lat, lon, start_date=a.start.isoformat(), end_date=a.end.isoformat())
            hist.to_csv(OUT / f"weather_hist_{lid}.csv", index=False)
            msg += f" hist {len(hist)} rows ({hist.datetimeLocal.min()} -> {hist.datetimeLocal.max()});"
        fc = get(FCST_URL, lat, lon, past_days=2, forecast_days=3)
        fc.to_csv(OUT / f"weather_fcst_{lid}.csv", index=False)
        print(msg, f"forecast {len(fc)} rows ({fc.datetimeLocal.min()} -> {fc.datetimeLocal.max()})")


if __name__ == "__main__":
    main()
