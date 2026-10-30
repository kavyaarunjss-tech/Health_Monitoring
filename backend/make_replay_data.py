"""Build data/replay.db for Replay mode from the saved research predictions (no retraining).

Why this is legitimate: for every forecast origin t, the models were fitted only on data that ended before the
period started (with an h-hour embargo), and the features at t use only data up to t (checked by
model/test_no_leakage.py). Replay therefore only reveals, hour by hour, predictions that were already made
out-of-sample.
  periods: 'validation' (fit on train only) and 'test' (refit on train+validation, scored once).

Time convention: aq_clean.py labels an hour by its START (row 14:00 = readings 14:00-14:59). The API converts
labels to hour-ENDING times for display (+1 h) so "now" is never ahead of the data.

Usage (project root, aqi env):  python backend/make_replay_data.py
"""
import pickle
import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "replay.db"
PREDS = [ROOT / "results" / "final" / "csh_preds.pkl"]   # official final run: horizons 1, 6, 12, 24, 36, 48, 72
PERIODS = {"validation": ("2026-04-17 07:00", "2026-05-29 13:00"),
           "test": ("2026-05-29 14:00", "2026-07-21 23:00")}


def main():
    frames = []
    for f in PREDS:
        for h, phases in pickle.load(open(f, "rb")).items():
            for phase, P in phases.items():
                period = {"val": "validation", "test": "test"}[phase]
                d = pd.DataFrame({
                    "period": period, "station": P["station"].values, "origin": pd.to_datetime(P["datetime"]).values,
                    "horizon": h, "ensemble": P["CSH-AQI ensemble"].values, "persistence": P["Persistence"].values,
                    "huber": P["Huber+Huber 3h (existing best)"].values, "y_true": P["y"].values,
                    "dominant": P["pred_dominant"].values if "pred_dominant" in P else None})
                frames.append(d)
    fc = pd.concat(frames, ignore_index=True)
    fc["origin"] = fc["origin"].dt.strftime("%Y-%m-%d %H:%M:%S")

    obs = pd.read_csv(ROOT / "data" / "processed" / "clean_hourly_all_stations.csv", parse_dates=["datetime"])
    # hourly PM2.5 / PM10 from 32 days before the validation period, for the "usually cleanest time of day" pattern (28-day window, backend/diurnal.py)
    pm = obs[(obs.datetime >= "2026-03-16") & (obs.datetime <= "2026-07-24")][["station", "datetime", "pm25", "pm10", "real_pm"]].copy()
    pm["datetime"] = pm["datetime"].dt.strftime("%Y-%m-%d %H:%M:%S")
    obs = obs[(obs.datetime >= "2026-04-10") & (obs.datetime <= "2026-07-24")]
    obs = obs[["station", "datetime", "AQI", "category", "dominant", "pm25", "pm10", "no2", "so2", "o3", "co",
               "pm25_si", "pm10_si", "no2_si", "so2_si", "o3_si", "co_si",
               "pm25_avg", "pm10_avg", "no2_avg", "so2_avg", "o3_avg", "co_avg"]].copy()
    obs["datetime"] = obs["datetime"].dt.strftime("%Y-%m-%d %H:%M:%S")

    with sqlite3.connect(DB) as con:
        fc.to_sql("replay_fc", con, if_exists="replace", index=False)
        obs.to_sql("replay_obs", con, if_exists="replace", index=False)
        pm.to_sql("replay_pm", con, if_exists="replace", index=False)
        con.execute("CREATE INDEX ix_pm ON replay_pm(station, datetime)")
        con.execute("CREATE INDEX ix_fc ON replay_fc(period, station, origin)")
        con.execute("CREATE INDEX ix_obs ON replay_obs(station, datetime)")
    print(f"wrote {DB}: {len(fc)} forecast rows, {len(obs)} observed hours")
    print(fc.groupby(["period", "horizon"]).size().unstack().to_string())


if __name__ == "__main__":
    main()
