"""Build the separate 36/48/72 h table from run_final.py prediction files, adding two seasonal-naive baselines:
  'Same hour 2/3 days ago' : AQI at the same hour of day as the target, the most recent whole number of days ago
                             (h=36 -> t-12 h; h=48 and h=72 -> AQI(t), i.e. equal to persistence by construction)
  'Same hour last week'    : AQI(t + h - 168 h)
usage: python long_horizon_table.py <hourly.pkl> <out.csv> <preds1.pkl> [<preds2.pkl> ...]"""
import sys, pickle
import numpy as np, pandas as pd
from aq_model import metrics

H = pd.read_pickle(sys.argv[1])
aqi = H.set_index(["station", "datetime"])["AQI"]
rows = []
for f in sys.argv[3:]:
    preds = pickle.load(open(f, "rb"))
    for h, phases in preds.items():
        k = int(np.ceil(h / 24))
        for phase, P in phases.items():
            P = P.copy()
            def look(shift_h):
                idx = pd.MultiIndex.from_arrays([P["station"], pd.to_datetime(P["datetime"]) + pd.Timedelta(hours=shift_h)])
                return aqi.reindex(idx).to_numpy(float)
            P["Same hour 2/3 days ago"] = look(h - 24 * k)
            P["Same hour last week"] = look(h - 168)
            models = ["Persistence", "Same hour 2/3 days ago", "Same hour last week", "Huber+Huber 3h (existing best)",
                      "CSH-AQI ensemble", "Direct GBM (anchored)", "Hybrid (anchored)", "Structural (anchored)"]
            ok = np.all([np.isfinite(P[m]) for m in models], axis=0) & np.isfinite(P["y"])   # same rows for every model
            for m in models:
                rows.append({"horizon": h, "split": phase, "model": m, "n": int(ok.sum()), **metrics(P.loc[ok, "y"], P.loc[ok, m])})
R = pd.DataFrame(rows)
R.to_csv(sys.argv[2], index=False)
pd.set_option("display.width", 200)
print(R[R.split == "test"].round(3).to_string(index=False))
