"""Likely-range rule for the website, from saved out-of-sample predictions (data/replay.db).

Rule (a design decision; the model is not touched):
  * error = actual AQI - forecast AQI, per horizon h and per forecast band (low <60, mid 60-100, high >=100)
  * shown range = [10th percentile, 90th percentile] of the error added to the forecast ("likely range, 80%")
  * for the high band the upper end uses the 95th percentile (wider upper tail where alerts matter)
  * a band with < 100 errors falls back to the horizon-level quantiles
Two versions:
  paper   : quantiles from VALIDATION only, coverage checked on TEST  (results/accuracy/range_rule_val_to_test.csv)
  website : quantiles from VALIDATION + TEST pooled (both out-of-sample) -> backend/ranges.json
usage: python make_quantiles.py   (project root or model/)
"""
import json
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
HORIZONS = (1, 6, 12, 24, 36, 48, 72)
BANDS = ("low", "mid", "high")


def band_of(f):
    return np.where(f < 60, "low", np.where(f < 100, "mid", "high"))


def fit(df, col="ensemble"):
    """{h: {band: [q_low, q_high, n]}} signed-error quantiles of (actual - df[col])."""
    out = {}
    for h in HORIZONS:
        x = df[df.horizon == h]
        e_all = (x.y_true - x[col]).to_numpy()
        base = np.percentile(e_all, [10, 90, 95])
        out[h] = {}
        for b in BANDS:
            e = e_all[band_of(x[col].to_numpy()) == b]
            if len(e) < 100:
                lo, hi, hi95 = base
            else:
                lo, hi, hi95 = np.percentile(e, [10, 90, 95])
            out[h][b] = [float(lo), float(hi95 if b == "high" else hi), int(len(e))]
    return out


def coverage(q, df):
    rows = []
    for h in HORIZONS:
        x = df[df.horizon == h]
        f, e = x.ensemble.to_numpy(), (x.y_true - x.ensemble).to_numpy()
        b = band_of(f)
        for name in ("all",) + BANDS:
            m = np.ones(len(e), bool) if name == "all" else (b == name)
            if m.sum() == 0:
                continue
            lo = np.array([q[h][bb][0] for bb in b[m]]); hi = np.array([q[h][bb][1] for bb in b[m]])
            rows.append({"horizon": h, "band": name, "n": int(m.sum()),
                         "coverage_%": 100 * float(((e[m] >= lo) & (e[m] <= hi)).mean()),
                         "mean_width": float((hi - lo).mean())})
    return pd.DataFrame(rows)


def main():
    con = sqlite3.connect(ROOT / "data" / "replay.db")
    D = pd.read_sql("select period,horizon,ensemble,persistence,y_true from replay_fc", con).dropna()
    val, test = D[D.period == "validation"], D[D.period == "test"]
    paper = coverage(fit(val), test)
    (ROOT / "results" / "accuracy").mkdir(parents=True, exist_ok=True)
    paper.to_csv(ROOT / "results" / "accuracy" / "range_rule_val_to_test.csv", index=False)
    print("PAPER VERSION: rule fitted on validation, coverage on test (nominal 80%; high band upper tail = 95th pct)")
    print(paper.pivot(index="horizon", columns="band", values="coverage_%").round(1).to_string())
    print("mean width:\n", paper.pivot(index="horizon", columns="band", values="mean_width").round(1).to_string())
    pooled = fit(D)
    pooled_pers = fit(D, "persistence")          # ranges for the persistence fallback (forecast = last observed AQI)
    (ROOT / "backend" / "ranges.json").write_text(json.dumps(
        {"rule": "signed error quantiles (actual-forecast): 10th/90th pct per horizon and forecast band; high band upper = 95th pct; "
                 "fitted on validation+test pooled", "bands": {"low": "<60", "mid": "60-100", "high": ">=100"},
         "ranges": {str(h): pooled[h] for h in HORIZONS},
         "persistence_ranges": {str(h): pooled_pers[h] for h in HORIZONS}}, indent=1), encoding="utf-8")
    print("\nwebsite ranges (pooled val+test) written to backend/ranges.json")
    for h in HORIZONS:
        print(h, {b: [round(pooled[h][b][0], 1), round(pooled[h][b][1], 1), pooled[h][b][2]] for b in BANDS})


if __name__ == "__main__":
    main()
