"""Final protocol.
Phase VAL : fit on train, evaluate on validation (model selection happens here).
Phase TEST: refit the same configuration on train+validation, evaluate test once.
usage: python run_final.py <hourly.pkl> <out_prefix>"""
import sys, time, pickle, json, hashlib, platform, subprocess, datetime
import numpy as np, pandas as pd
from aq_model import *
import aq_model


def run_info(src, horizons):
    """Everything needed to reproduce this run (written next to the results)."""
    import sklearn, scipy
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True).stdout.strip())
    except Exception:
        commit, dirty = "unknown", None
    info = {"started": datetime.datetime.now().isoformat(timespec="seconds"), "python": platform.python_version(),
            "numpy": np.__version__, "pandas": pd.__version__, "sklearn": sklearn.__version__, "scipy": scipy.__version__,
            "learner": "LightGBM" if aq_model.HAVE_LGB else "sklearn HistGradientBoostingRegressor",
            "git_commit": commit, "git_dirty": dirty, "horizons": horizons, "FAST": False,
            "n_iter": 300, "n_folds": 4, "learning_rate": 0.05, "num_leaves": 31, "min_samples_leaf": 40, "l2": 1.0,
            "seeds": "Hybrid: stage A seed 0, stage C seed 1; Direct GBM seed 0; members share the configuration",
            "split": {"val_start": str(VAL_START), "test_start": str(TEST_START), "test_end": str(TEST_END)},
            "input_file": str(src), "input_sha256": hashlib.sha256(open(src, "rb").read()).hexdigest()}
    from pathlib import Path
    csv = Path(src).with_suffix(".csv")           # the cleaned CSV the pickle was made from
    if csv.exists():
        info["source_csv"] = str(csv)
        info["source_csv_sha256"] = hashlib.sha256(csv.read_bytes()).hexdigest()
    if aq_model.HAVE_LGB:
        import lightgbm
        info["lightgbm"] = lightgbm.__version__
    return info

MEMBERS = ["Structural", "Structural (anchored)", "Hybrid", "Hybrid (anchored)", "Direct GBM", "Direct GBM (anchored)"]


def fit_predict(Dfit, Deval, cols, h):
    out = {"Persistence": Deval["AQI"].to_numpy(float)}
    hb = Huber3h().fit(Dfit)
    out["Huber+Huber 3h (existing best)"] = hb.predict(Deval)
    for anch in (False, True):
        tag = " (anchored)" if anch else ""
        hy = CPCBStructuredHybrid(h, anchored=anch).fit(Dfit, cols)
        f, s, dom = hy.predict(Deval, cols, return_parts=True)
        out["Structural" + tag] = np.clip(s, 0, 500)
        out["Hybrid" + tag] = f
        out["Direct GBM" + tag] = DirectGBM(anchored=anch).fit(Dfit, cols).predict(Deval, cols)
        if anch:
            out["pred_dominant"] = dom
    out["CSH-AQI ensemble"] = np.mean([out[m] for m in MEMBERS], axis=0)
    return out


src, prefix = sys.argv[1], sys.argv[2]
H = pd.read_pickle(src)
# optional 4th argument: "YYYY-MM-DD:YYYY-MM-DD" -> use ONLY data inside this window (features and targets)
if len(sys.argv) > 4 and sys.argv[4]:
    a, b = sys.argv[4].split(":")
    H = H[(H["datetime"] >= pd.Timestamp(a)) & (H["datetime"] <= pd.Timestamp(b) + pd.Timedelta(hours=23))]
    print(f"Data window: {a} to {b}  ({len(H)} station-hours)", flush=True)
results, preds = [], {}
HZ = [int(x) for x in sys.argv[3].split(",")] if len(sys.argv) > 3 else HORIZONS
INFO = run_info(src, HZ)
print("run info:", json.dumps({k: INFO[k] for k in ("python", "pandas", "sklearn", "learner", "git_commit", "git_dirty")}), flush=True)
for h in HZ:
    t0 = time.time()
    D = build_dataset(H, h)
    cols = feature_columns(D)
    tr, va, te = split_masks(D, h)
    yok = np.isfinite(D["y"]).to_numpy()
    ev = yok & np.isfinite(D["AQI"]).to_numpy()
    trval = (D["datetime"] < TEST_START - pd.Timedelta(hours=h)).to_numpy()
    preds[h] = {}
    for phase, fit_mask, ev_mask in [("val", tr & yok, va & ev), ("test", trval & yok, te & ev)]:
        Dfit, Dev = D[fit_mask], D[ev_mask]
        use_cols = drop_season_if_short(cols, Dfit)
        print(f"  h={h} {phase}: seasonal features {'kept' if len(use_cols) == len(cols) else 'dropped (training < 1 year)'}", flush=True)
        o = fit_predict(Dfit, Dev, use_cols, h)
        P = pd.DataFrame({"datetime": Dev["datetime"].values, "station": Dev["station"].values,
                          "y": Dev["y"].values, "true_dominant": None, **o})
        preds[h][phase] = P
        for m in [k for k in o if k != "pred_dominant"]:
            results.append({"horizon": h, "split": phase, "model": m, "n": len(P), **metrics(P["y"], P[m])})
        print(f"h={h} {phase}: fit rows {len(Dfit)}, eval rows {len(Dev)}, {time.time()-t0:.0f}s", flush=True)
    R = pd.DataFrame(results)
    print(R[R.horizon == h].drop(columns="horizon").round(3).to_string(index=False), flush=True)
    pd.DataFrame(results).to_csv(f"{prefix}_metrics.csv", index=False)
    with open(f"{prefix}_preds.pkl", "wb") as fh:
        pickle.dump(preds, fh)
INFO["finished"] = datetime.datetime.now().isoformat(timespec="seconds")
json.dump(INFO, open(f"{prefix}_run_info.json", "w"), indent=1)
print("ALL DONE", flush=True)
