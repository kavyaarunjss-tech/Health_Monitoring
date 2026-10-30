"""Write the current live forecasts to data/aqi.db (table live_forecast) from each station's newest valid observation.

Per station: origin = newest hour with a valid AQI. For every horizon: the saved CSH-AQI model if models/live/h<h>.joblib exists,
otherwise the PERSISTENCE FALLBACK (forecast = last observed AQI) with method = 'persistence'. Nothing is invented: if a station has no
valid AQI in the last 7 days it gets no forecast.
usage (project root, aqi env): python backend/forecast_live.py
"""
import datetime as dt
import sqlite3

import joblib
import numpy as np
import pandas as pd

import live_model as lm

DB = lm.ROOT / "data" / "aqi.db"
MAX_AGE_DAYS = 7


def main():
    with sqlite3.connect(DB) as con:
        hourly = pd.read_sql("select * from hourly", con, parse_dates=["datetime"])
    now = dt.datetime.now()
    origins = {}
    for st, g in hourly.dropna(subset=["AQI"]).groupby("station"):
        t = g["datetime"].max()
        if (now - t.to_pydatetime()).days <= MAX_AGE_DAYS:
            origins[st] = t
    rows = []
    for h in lm.HORIZONS:
        path = lm.model_path(h)
        obj = joblib.load(path) if path.exists() else None
        pers = {}
        for st, t in origins.items():
            pers[st] = float(hourly[(hourly.station == st) & (hourly.datetime == t)]["AQI"].iloc[0])
        if obj is not None:
            D = lm.am.build_dataset(hourly, h)
            for st, t in origins.items():
                R = D[(D.station == st) & (D.datetime == t)]
                if len(R) != 1:
                    continue
                ens, dom = lm.predict(obj, R)
                rows.append((st, str(t), h, "model", float(ens[0]), str(dom[0]), pers[st], obj["trained_through"]))
        for st, t in origins.items():
            if not any(r[0] == st and r[2] == h for r in rows):         # no model, or the model could not run: fallback
                rows.append((st, str(t), h, "persistence", pers[st], None, pers[st], None))
    out = pd.DataFrame(rows, columns=["station", "origin", "horizon", "method", "aqi", "dominant", "persistence", "trained_through"])
    out["generated_at"] = now.strftime("%Y-%m-%d %H:%M:%S")
    with sqlite3.connect(DB, timeout=60) as con:
        out.to_sql("live_forecast", con, if_exists="replace", index=False)
    print(out.groupby(["station", "method"]).size().unstack(fill_value=0).to_string())
    print("origins:", {k: str(v) for k, v in origins.items()})


if __name__ == "__main__":
    main()
