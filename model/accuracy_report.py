"""Accuracy table per horizon from saved out-of-sample predictions (no retraining, no tuning).
Rows: forecast origins whose target AQI is CPCB-valid and whose current AQI exists (same rows for both models).
usage: python accuracy_report.py   (reads data/replay.db; writes results/accuracy/*.csv)"""
import sqlite3
import numpy as np, pandas as pd
from sklearn.metrics import r2_score

EDGES = [50, 100, 200, 300, 400]
def cat(a): return np.searchsorted(EDGES, np.asarray(a, float), side="left")   # 0 Good ... 5 Severe

con = sqlite3.connect("data/replay.db")
D = pd.read_sql("select period,station,origin,horizon,ensemble,persistence,y_true from replay_fc", con)
D = D.dropna(subset=["ensemble", "persistence", "y_true"])

def row(y, p):
    e = np.abs(y - p); cy, cp = cat(y), cat(p)
    return {"n": len(y), "R2": r2_score(y, p), "MAE": e.mean(), "Cat_exact_%": 100 * (cy == cp).mean(),
            "Cat_within1_%": 100 * (np.abs(cy - cp) <= 1).mean(), "within10_%": 100 * (e <= 10).mean(), "within20_%": 100 * (e <= 20).mean()}

out = []
for period in ("test", "validation"):
    for h in (1, 6, 12, 24, 36, 48, 72):
        x = D[(D.period == period) & (D.horizon == h)]
        for name, col in (("CSH-AQI", "ensemble"), ("Persistence", "persistence")):
            out.append({"period": period, "horizon": h, "model": name, **row(x.y_true.to_numpy(), x[col].to_numpy())})
R = pd.DataFrame(out)
R.to_csv("results/accuracy/accuracy_by_horizon.csv", index=False)
pd.set_option("display.width", 220)
for period in ("test", "validation"):
    print(f"\n=== {period.upper()} ===")
    print(R[R.period == period].drop(columns="period").round(3).to_string(index=False))

# ---- error quantiles from VALIDATION, coverage checked on TEST (signed error = actual - forecast) ----
rows = []
band = lambda f: np.where(f < 60, "low (<60)", np.where(f < 100, "mid (60-100)", "high (>=100)"))
for h in (1, 6, 12, 24, 36, 48, 72):
    v = D[(D.period == "validation") & (D.horizon == h)]; t = D[(D.period == "test") & (D.horizon == h)]
    ev = (v.y_true - v.ensemble).to_numpy(); et = (t.y_true - t.ensemble).to_numpy()
    for lvl, (lo, hi) in {"80%": (10, 90), "90%": (5, 95)}.items():
        ql, qh = np.percentile(ev, [lo, hi])
        cov = ((et >= ql) & (et <= qh)).mean() * 100
        rows.append({"horizon": h, "interval": lvl, "val_q_low": ql, "val_q_high": qh, "width": qh - ql, "test_coverage_%": cov,
                     "val_n": len(ev), "test_n": len(et)})
Q = pd.DataFrame(rows); Q.to_csv("results/accuracy/error_quantiles_val_to_test.csv", index=False)
print("\n=== Error quantiles from validation (actual - forecast), coverage on test ===")
print(Q.round(1).to_string(index=False))

# band-conditional (error depends on level): 80% interval per forecast band
rows = []
for h in (1, 6, 12, 24, 36, 48, 72):
    v = D[(D.period == "validation") & (D.horizon == h)].copy(); t = D[(D.period == "test") & (D.horizon == h)].copy()
    v["b"], t["b"] = band(v.ensemble.to_numpy()), band(t.ensemble.to_numpy())
    for b in ["low (<60)", "mid (60-100)", "high (>=100)"]:
        vb, tb = v[v.b == b], t[t.b == b]
        if len(vb) < 100: rows.append({"horizon": h, "band": b, "val_n": len(vb), "test_n": len(tb)}); continue
        ev = (vb.y_true - vb.ensemble).to_numpy(); ql, qh = np.percentile(ev, [10, 90])
        et = (tb.y_true - tb.ensemble).to_numpy()
        rows.append({"horizon": h, "band": b, "val_n": len(vb), "test_n": len(tb), "q10": ql, "q90": qh,
                     "test_cov80_%": 100 * ((et >= ql) & (et <= qh)).mean() if len(et) else np.nan})
B = pd.DataFrame(rows); B.to_csv("results/accuracy/error_quantiles_by_band.csv", index=False)
print("\n=== 80% interval by forecast band (validation quantiles; test coverage) ===")
print(B.round(1).to_string(index=False))
