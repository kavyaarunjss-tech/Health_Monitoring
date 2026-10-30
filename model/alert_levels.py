"""Two-level alert evaluation from saved out-of-sample predictions (data/replay.db). No model is changed.

  Likely   : forecast AQI >= threshold
  Possible : forecast AQI < threshold but the upper end of the likely range >= threshold
Event = actual AQI at the target hour >= threshold (CPCB-valid targets only).
Ranges for the TEST period are fitted on VALIDATION only (honest). For the validation period the ranges are fitted on
validation itself, so those rows are in-sample for the ranges (flagged).
usage: python alert_levels.py   -> results/accuracy/alert_levels.csv
"""
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model"))
from make_quantiles import fit, band_of, HORIZONS  # noqa: E402

D = pd.read_sql("select period,station,origin,horizon,ensemble,y_true from replay_fc",
                sqlite3.connect(ROOT / "data" / "replay.db")).dropna()
Q = fit(D[D.period == "validation"])          # ranges fitted on validation only
hi_off = {h: {b: Q[h][b][1] for b in Q[h]} for h in Q}


def evaluate(x, thr, h):
    f, y = x.ensemble.to_numpy(), x.y_true.to_numpy()
    hi = f + np.array([hi_off[h][b] for b in band_of(f)])
    likely, possible = f >= thr, (f < thr) & (hi >= thr)
    ev = y >= thr
    # onset hours: first hour of an event run per station (target hours t+h; consecutive hours merged)
    t = pd.to_datetime(x.origin) + pd.Timedelta(hours=h)
    d = pd.DataFrame({"st": x.station.to_numpy(), "t": t.to_numpy(), "ev": ev}).sort_values(["st", "t"])
    prev_ev = d.groupby("st").ev.shift(1, fill_value=False)
    prev_t = d.groupby("st").t.shift(1)
    onset = d.ev & ~(prev_ev & ((d.t - prev_t) == pd.Timedelta(hours=1)))
    onset_idx = d.index[onset.to_numpy()]
    pos = {i: k for k, i in enumerate(x.index)}       # map back to x order
    on = np.zeros(len(x), bool); on[[pos[i] for i in onset_idx]] = True
    n_ev = int(ev.sum())
    out = {"events(hours)": n_ev, "event_onsets": int(on.sum()), "n_forecasts": len(x),
           "likely_alerts": int(likely.sum()), "possible_alerts": int(possible.sum())}
    for name, m in (("Likely", likely), ("Likely+Possible", likely | possible)):
        tp = int((m & ev).sum())
        out[f"{name}: hit_rate_%"] = 100 * tp / n_ev if n_ev else np.nan
        out[f"{name}: onset_hit_%"] = 100 * int((m & on).sum()) / int(on.sum()) if on.sum() else np.nan
        out[f"{name}: false_alarm_%_of_alerts"] = 100 * (int(m.sum()) - tp) / int(m.sum()) if m.sum() else np.nan
    pm = possible
    out["Possible only: precision_%"] = 100 * int((pm & ev).sum()) / int(pm.sum()) if pm.sum() else np.nan
    return out


rows = []
for period in ("test", "validation"):
    for thr in (101, 201):
        for h in HORIZONS:
            x = D[(D.period == period) & (D.horizon == h)].reset_index(drop=True)
            rows.append({"period": period, "threshold": thr, "horizon": h,
                         "ranges": "fitted on validation (honest)" if period == "test" else "fitted on validation (in-sample)",
                         **evaluate(x, thr, h)})
R = pd.DataFrame(rows)
R.to_csv(ROOT / "results" / "accuracy" / "alert_levels.csv", index=False)
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)
cols = ["horizon", "events(hours)", "event_onsets", "likely_alerts", "possible_alerts", "Likely: hit_rate_%", "Likely: onset_hit_%",
        "Likely: false_alarm_%_of_alerts", "Likely+Possible: hit_rate_%", "Likely+Possible: onset_hit_%",
        "Likely+Possible: false_alarm_%_of_alerts", "Possible only: precision_%"]
for (p, t), g in R.groupby(["period", "threshold"], sort=False):
    print(f"\n=== {p.upper()}  threshold AQI >= {t} ===")
    print(g[cols].round(1).to_string(index=False))
