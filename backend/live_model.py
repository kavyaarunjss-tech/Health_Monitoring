"""Live model helpers: train CSH-AQI on all available data, and predict from each station's newest observation.

Same 6-member equal-weight ensemble as the research model (Structural, Hybrid, Direct GBM, each plain and anchored), same
configuration as the official run (300 trees, 4 folds, LightGBM). Differences from research evaluation: no validation/test split and no
embargo (nothing is evaluated here); trained on every row whose target is known.
Models are saved to models/live/h<h>.joblib (git-ignored).
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model"))
import aq_model as am  # noqa: E402

MODEL_DIR = ROOT / "models" / "live"
HORIZONS = (1, 6, 12, 24, 36, 48, 72)
MEMBERS = ["Structural", "Structural (anchored)", "Hybrid", "Hybrid (anchored)", "Direct GBM", "Direct GBM (anchored)"]


def model_path(h):
    return MODEL_DIR / f"h{h}.joblib"


def train(hourly, h):
    """Fit the four fitted objects (plain/anchored hybrid and direct GBM) for horizon h on all rows with a known target."""
    D = am.build_dataset(hourly, h)
    cols = am.feature_columns(D)
    Dfit = D[np.isfinite(D["y"].to_numpy())]
    use_cols = am.drop_season_if_short(cols, Dfit)
    obj = {"h": h, "cols": use_cols, "trained_through": str(Dfit["datetime"].max()), "n_rows": int(len(Dfit)), "hybrid": {}, "direct": {}}
    for anch in (False, True):
        obj["hybrid"][anch] = am.CPCBStructuredHybrid(h, anchored=anch).fit(Dfit, use_cols)
        obj["direct"][anch] = am.DirectGBM(anchored=anch).fit(Dfit, use_cols)
    return obj


def predict(obj, D_rows):
    """Ensemble forecast and dominant pollutant for the rows of D_rows (features at the forecast origin)."""
    cols, out = obj["cols"], {}
    for anch in (False, True):
        tag = " (anchored)" if anch else ""
        f, s, dom = obj["hybrid"][anch].predict(D_rows, cols, return_parts=True)
        out["Structural" + tag] = np.clip(s, 0, 500)
        out["Hybrid" + tag] = f
        out["Direct GBM" + tag] = obj["direct"][anch].predict(D_rows, cols)
        if anch:
            dominant = dom
    ens = np.mean([out[m] for m in MEMBERS], axis=0)
    return ens, dominant
