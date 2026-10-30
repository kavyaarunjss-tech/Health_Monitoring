"""Train the live models (one file per horizon) from data/aqi.db. SLOW: about 6 minutes per horizon (7 horizons ~ 45 min).
usage (project root, aqi env): python backend/train_live.py [h1,h2,...]"""
import sqlite3
import sys
import time

import joblib
import pandas as pd

import live_model as lm

hs = [int(x) for x in sys.argv[1].split(",")] if len(sys.argv) > 1 else list(lm.HORIZONS)
with sqlite3.connect(lm.ROOT / "data" / "aqi.db") as con:
    hourly = pd.read_sql("select * from hourly", con, parse_dates=["datetime"])
print(f"training on {len(hourly)} station-hours, {hourly.datetime.min()} -> {hourly.datetime.max()}", flush=True)
lm.MODEL_DIR.mkdir(parents=True, exist_ok=True)
for h in hs:
    t = time.time()
    obj = lm.train(hourly, h)
    joblib.dump(obj, lm.model_path(h))
    print(f"h={h}: trained on {obj['n_rows']} rows (through {obj['trained_through']}), saved, {time.time() - t:.0f} s", flush=True)
print("ALL DONE")
