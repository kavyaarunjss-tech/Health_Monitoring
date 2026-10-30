"""
Step 2 - CPCB-Structured Hybrid forecaster (CSH-AQI) + baselines.

Idea
----
CPCB AQI at time t+h is not an arbitrary number: it is
    AQI(t+h) = max_p  SI_p( running-average_p(t+h) )
where the running average is 24 h for PM2.5/PM10/NO2/SO2 and 8 h for O3/CO.
For a forecast made at time t, part of every running window is ALREADY
OBSERVED (hours t+h-23 ... t) and only the last h hours are unknown.

The hybrid therefore
  Stage A  forecasts, for every pollutant, only the unknown part of its window
           (mean concentration over hours t+1 ... t+h) with a gradient-boosted
           model,
  Stage B  rebuilds the running averages exactly (known part + forecast part)
           and applies the official CPCB sub-index + max rule -> "structural"
           AQI forecast, plus the dominant pollutant,
  Stage C  a second gradient-boosted model learns the residual
           (true AQI - structural AQI) from the structural outputs and context
           features (out-of-fold, so it never sees its own training fit).
Final forecast = structural AQI + residual correction.

Baselines: persistence, a replica of the existing best (Huber on 3 h window),
and a direct gradient-boosted AQI model with the same features (ablation).
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import HuberRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from aq_clean import POLLUTANTS, aqi_from_averages, aqi_category

try:                                   # use LightGBM when available (same algorithm family)
    import lightgbm as lgb
    HAVE_LGB = True
except Exception:
    HAVE_LGB = False

HORIZONS = [1, 6, 12, 24]
AVG24 = ["pm25", "pm10", "no2", "so2"]
AVG8 = ["o3", "co"]


def gbm(seed=0, loss="squared_error", n_iter=400, lr=0.05):
    if HAVE_LGB:
        return lgb.LGBMRegressor(n_estimators=n_iter, learning_rate=lr, num_leaves=31,
                                 min_child_samples=40, subsample=0.8, subsample_freq=1,
                                 colsample_bytree=0.8, reg_lambda=1.0, random_state=seed,
                                 objective="regression" if loss == "squared_error" else "huber",
                                 deterministic=True, force_row_wise=True,   # reproducible runs (same seed -> same model)
                                 verbose=-1)
    return HistGradientBoostingRegressor(loss=loss, max_iter=n_iter, learning_rate=lr,
                                         max_leaf_nodes=31, min_samples_leaf=40,
                                         l2_regularization=1.0, max_features=0.8,
                                         early_stopping=False, random_state=seed)


# ---------------------------------------------------------------------------
# Feature engineering (all features use information available at time t only)
# ---------------------------------------------------------------------------
def _station_base(s):
    """s: one station, hourly grid, sorted. Returns base feature frame."""
    f = pd.DataFrame(index=s.index)
    conc = POLLUTANTS + ["no", "nox"]
    for c in conc:
        x = s[c]
        f[c] = x
        for L in (1, 2, 3, 6, 12, 23):
            f[f"{c}_lag{L}"] = x.shift(L)
        for w in (3, 6, 12, 24):
            f[f"{c}_mean{w}"] = x.rolling(w, min_periods=max(1, w // 2)).mean()
        f[f"{c}_std24"] = x.rolling(24, min_periods=12).std()
        f[f"{c}_d1"] = x - x.shift(1)
        f[f"{c}_d3"] = x - x.shift(3)
    for p in POLLUTANTS:
        f[f"{p}_avg"] = s[f"{p}_avg"]
        f[f"{p}_si"] = s[f"{p}_si"]
    a = s["AQI"]
    f["AQI"] = a
    for L in (1, 2, 3, 6, 12, 24, 48, 168):
        f[f"AQI_lag{L}"] = a.shift(L)
    f["AQI_d1"], f["AQI_d3"], f["AQI_d24"] = a - a.shift(1), a - a.shift(3), a - a.shift(24)
    f["AQI_std24"] = a.rolling(24, min_periods=12).std()
    for c in ["temperature", "relativehumidity", "wind_speed", "wind_u", "wind_v"]:
        x = s[c] if c in s else pd.Series(np.nan, index=s.index)
        f[c] = x
        f[f"{c}_lag1"], f[f"{c}_lag2"] = x.shift(1), x.shift(2)
        f[f"{c}_mean6"] = x.rolling(6, min_periods=3).mean()
        f[f"{c}_mean24"] = x.rolling(24, min_periods=12).mean()
    f["temp_d24"] = f["temperature"] - f["temperature"].shift(24)
    f["rh_d24"] = f["relativehumidity"] - f["relativehumidity"].shift(24)
    if "real_pm" in s:
        f["real_share24"] = s["real_pm"].rolling(24, min_periods=1).mean()
    t = s.index
    f["hour_sin"], f["hour_cos"] = np.sin(2 * np.pi * t.hour / 24), np.cos(2 * np.pi * t.hour / 24)
    f["dow"] = t.dayofweek
    f["weekend"] = (t.dayofweek >= 5).astype(int)
    f["doy_sin"], f["doy_cos"] = np.sin(2 * np.pi * t.dayofyear / 365.25), np.cos(2 * np.pi * t.dayofyear / 365.25)
    return f


def _station_horizon(s, h):
    """Horizon-specific features, structural 'known parts' and targets."""
    f = pd.DataFrame(index=s.index)
    tt = s.index + pd.Timedelta(hours=h)
    f["tgt_hour_sin"], f["tgt_hour_cos"] = np.sin(2 * np.pi * tt.hour / 24), np.cos(2 * np.pi * tt.hour / 24)
    f["tgt_dow"] = tt.dayofweek
    known, unknown_target = {}, {}
    # "same hour / window one day (or two, three...) earlier": the smallest whole number of days so that it
    # ends at or before t. For h <= 24 this is 24 - h (unchanged); for h > 24 it must not be negative,
    # otherwise the feature would look into the future (found by test_no_leakage.py).
    day_lag = 24 * int(np.ceil(h / 24)) - h
    for p in POLLUTANTS:
        x = s[p]
        W = 24 if p in AVG24 else 8
        K = max(0, W - h)                 # observed hours that remain in the window at t+h
        L = min(h, W)                     # hours of the window that are still in the future
        if K > 0:
            known[p] = x.rolling(K, min_periods=1).mean()
            f[f"{p}_known_mean"] = known[p]
            f[f"{p}_known_n"] = x.notna().astype(float).rolling(K, min_periods=1).sum()
        else:
            known[p] = pd.Series(np.nan, index=s.index)
        # same window yesterday / last week (fully observed at time t)
        f[f"{p}_win_yday"] = x.rolling(L, min_periods=max(1, L // 2)).mean().shift(day_lag)
        f[f"{p}_at_tgt_yday"] = x.shift(day_lag)
        f[f"{p}_at_tgt_wk"] = x.shift(168 - h)
        # Stage-A target: mean of the future (unknown) hours of the window
        unknown_target[p] = x.rolling(L, min_periods=int(np.ceil(0.75 * L))).mean().shift(-h)
    f["AQI_at_tgt_yday"] = s["AQI"].shift(day_lag)
    f["AQI_at_tgt_wk"] = s["AQI"].shift(168 - h)
    y = s["AQI"].shift(-h)
    return f, known, unknown_target, y


def build_dataset(hourly, h):
    """hourly: all stations, columns incl. datetime, station, pollutants, *_avg, *_si, AQI."""
    parts = []
    for st, s in hourly.groupby("station", sort=True):
        s = s.set_index("datetime").sort_index()
        s = s[~s.index.duplicated()].asfreq("1h")
        s["station"] = st
        base = _station_base(s)
        hf, known, unk, y = _station_horizon(s, h)
        d = pd.concat([base, hf], axis=1)
        for p in POLLUTANTS:
            d[f"KNOWN_{p}"] = known[p]
            d[f"UNK_{p}"] = unk[p]
            # anchor = current 24 h level of the pollutant (for scale-free targets)
            d[f"ANCH_{p}"] = s[p].rolling(24, min_periods=6).mean()
        d["y"] = y
        d["station"] = st
        parts.append(d.reset_index().rename(columns={"index": "datetime"}))
    D = pd.concat(parts, ignore_index=True)
    D["station_code"] = D["station"].astype("category").cat.codes
    return D


def feature_columns(D):
    drop = {"datetime", "station", "y"} | {c for c in D if c.startswith(("KNOWN_", "UNK_", "ANCH_"))}
    # drop columns with no data at all (e.g. wind when a dataset has no wind sensor)
    return [c for c in D.columns if c not in drop and D[c].notna().any()]


def drop_season_if_short(cols, D_fit, min_days=330):
    """Day-of-year features are only meaningful when the training data covers a
    full annual cycle; with less, trees extrapolate the season edge to unseen
    dates. Drop them in that case."""
    span = (D_fit["datetime"].max() - D_fit["datetime"].min()).days
    return cols if span >= min_days else [c for c in cols if not c.startswith("doy")]


# ---------------------------------------------------------------------------
# Splits (same calendar boundaries as the original notebook, plus an embargo)
# ---------------------------------------------------------------------------
VAL_START = pd.Timestamp("2026-04-17 07:00")
TEST_START = pd.Timestamp("2026-05-29 14:00")
TEST_END = pd.Timestamp("2026-07-21 23:00")


def split_masks(D, h, train_from=None):
    t = D["datetime"]
    emb = pd.Timedelta(hours=h)            # target of a training row must end before validation starts
    tr = t < VAL_START - emb
    if train_from is not None:
        tr &= t >= pd.Timestamp(train_from)
    va = (t >= VAL_START) & (t < TEST_START - emb)
    te = (t >= TEST_START) & (t <= TEST_END)
    return tr.to_numpy(), va.to_numpy(), te.to_numpy()


# ---------------------------------------------------------------------------
# Structural reconstruction of CPCB AQI from forecast concentrations
# ---------------------------------------------------------------------------
def structural_aqi(D, unk_pred, h):
    avgs = {}
    for p in POLLUTANTS:
        W = 24 if p in AVG24 else 8
        K, L = max(0, W - h), min(h, W)
        kn = D[f"KNOWN_{p}"].to_numpy(float)
        fu = np.asarray(unk_pred[p], float)
        if K > 0:
            avg = np.where(np.isfinite(kn), (K * kn + L * fu) / W, fu)
            # CPCB minimum data rule (16 of 24 h, 6 of 8 h): observed hours + forecast hours
            n_obs = D[f"{p}_known_n"].to_numpy(float) if f"{p}_known_n" in D else np.full(len(D), K)
            avg = np.where(np.nan_to_num(n_obs) + L >= int(np.ceil(W * 2 / 3)), avg, np.nan)
        else:
            avg = fu
        avgs[p] = avg
    aqi, si = aqi_from_averages(avgs)
    # fall back to max of available sub-indices if CPCB 3-pollutant rule fails in forecast space
    S = np.column_stack([si[p] for p in POLLUTANTS])
    with np.errstate(all="ignore"):
        any_aqi = np.nanmax(np.where(np.isfinite(S), S, -np.inf), axis=1)
    aqi = np.where(np.isfinite(aqi), aqi, np.where(np.isfinite(any_aqi), any_aqi, np.nan))
    return aqi, si, avgs


class CPCBStructuredHybrid:
    """Stage A (per-pollutant future-window forecasters) -> Stage B (exact CPCB
    reconstruction) -> Stage C (residual corrector trained out-of-fold)."""

    def __init__(self, h, n_folds=4, n_iter=300, seed=0, anchored=True):
        self.h, self.n_folds, self.n_iter, self.seed = h, n_folds, n_iter, seed
        self.anchored = anchored
        self.fill = {}

    def _anchor(self, D, p):
        a = D[f"ANCH_{p}"].to_numpy(float)
        return np.where(np.isfinite(a), a, self.fill.get(p, np.nan))

    def _fit_stage_a(self, X, D):
        models = {}
        for p in POLLUTANTS:
            yt = D[f"UNK_{p}"].to_numpy(float)
            m = np.isfinite(yt)
            if m.sum() < 500:
                models[p] = None
                continue
            target = np.log1p(np.clip(yt, 0, None))
            if self.anchored:            # forecast log-ratio of future level to current level
                target = target - np.log1p(self._anchor(D, p))
                m &= np.isfinite(target)
            mdl = gbm(self.seed, n_iter=self.n_iter)
            mdl.fit(X[m], target[m])
            models[p] = mdl
        return models

    def _predict_stage_a(self, models, X, D):
        out = {}
        for p in POLLUTANTS:
            if models[p] is None:
                out[p] = D[f"KNOWN_{p}"].to_numpy(float)  # fallback: assume level persists
            else:
                z = models[p].predict(X)
                if self.anchored:
                    z = z + np.log1p(self._anchor(D, p))
                out[p] = np.expm1(z)
        return out

    def _stage_c_features(self, X, D, unk_pred):
        aqi_s, si, avgs = structural_aqi(D, unk_pred, self.h)
        extra = [aqi_s] + [si[p] for p in POLLUTANTS] + [avgs[p] for p in POLLUTANTS] + [unk_pred[p] for p in POLLUTANTS]
        return np.column_stack([X] + extra), aqi_s

    def fit(self, D_tr, cols):
        X = D_tr[cols].to_numpy(np.float32)
        self.fill = {p: float(np.nanmedian(D_tr[f"ANCH_{p}"])) for p in POLLUTANTS}
        # out-of-fold Stage-A predictions on the training set (contiguous time blocks)
        order = np.argsort(D_tr["datetime"].to_numpy())
        folds = np.array_split(order, self.n_folds)
        oof = {p: np.full(len(D_tr), np.nan) for p in POLLUTANTS}
        for k in range(self.n_folds):
            hold = folds[k]
            fit_idx = np.concatenate([folds[j] for j in range(self.n_folds) if j != k])
            mods = self._fit_stage_a(X[fit_idx], D_tr.iloc[fit_idx])
            pr = self._predict_stage_a(mods, X[hold], D_tr.iloc[hold])
            for p in POLLUTANTS:
                oof[p][hold] = pr[p]
        self.stage_a = self._fit_stage_a(X, D_tr)
        Xc, aqi_s = self._stage_c_features(X, D_tr, oof)
        y = D_tr["y"].to_numpy(float)
        m = np.isfinite(y) & np.isfinite(aqi_s)
        self.stage_c = gbm(self.seed + 1, n_iter=self.n_iter)
        self.stage_c.fit(Xc[m], (y - aqi_s)[m])
        return self

    def predict(self, D, cols, return_parts=False):
        X = D[cols].to_numpy(np.float32)
        unk = self._predict_stage_a(self.stage_a, X, D)
        Xc, aqi_s = self._stage_c_features(X, D, unk)
        final = aqi_s + self.stage_c.predict(Xc)
        final = np.clip(final, 0, 500)
        if return_parts:
            _, si, _ = structural_aqi(D, unk, self.h)
            S = np.column_stack([si[p] for p in POLLUTANTS])
            dom = np.array(POLLUTANTS, dtype=object)[np.argmax(np.where(np.isfinite(S), S, -1), axis=1)]
            return final, aqi_s, dom
        return final


# ---------------------------------------------------------------------------
# Baselines
# ---------------------------------------------------------------------------
HUBER_FEATS = ["pm25", "pm10", "no", "no2", "nox", "co", "o3", "so2", "temperature", "relativehumidity", "AQI"]


def huber3h_features(D):
    """Same inputs as the existing notebook: 11 variables at t-2, t-1, t."""
    cols = []
    for c in HUBER_FEATS:
        cols += [f"{c}_lag2", f"{c}_lag1", c]
    return D[cols].to_numpy(float)


class Huber3h:
    """Replica of the existing best model: two Huber regressors on the last 3 hours, averaged."""

    def fit(self, D_tr):
        X = huber3h_features(D_tr)
        y = D_tr["y"].to_numpy(float)
        self.imp = SimpleImputer(strategy="median").fit(X)
        self.sc = StandardScaler().fit(self.imp.transform(X))
        Xs = self.sc.transform(self.imp.transform(X))
        m = np.isfinite(y)
        self.m1 = HuberRegressor(epsilon=1.35, alpha=1e-4, max_iter=500).fit(Xs[m], y[m])
        self.m2 = HuberRegressor(epsilon=1.5, alpha=1e-3, max_iter=500).fit(Xs[m], y[m])
        return self

    def predict(self, D):
        Xs = self.sc.transform(self.imp.transform(huber3h_features(D)))
        return (self.m1.predict(Xs) + self.m2.predict(Xs)) / 2


class DirectGBM:
    """Gradient boosting on AQI directly. anchored=True learns the change
    AQI(t+h) - AQI(t) instead of the level."""

    def __init__(self, n_iter=300, seed=0, anchored=False):
        self.n_iter, self.seed, self.anchored = n_iter, seed, anchored

    def fit(self, D_tr, cols):
        y = D_tr["y"].to_numpy(float)
        if self.anchored:
            y = y - D_tr["AQI"].to_numpy(float)
        m = np.isfinite(y)
        self.m = gbm(self.seed, n_iter=self.n_iter).fit(D_tr[cols].to_numpy(np.float32)[m], y[m])
        return self

    def predict(self, D, cols):
        p = self.m.predict(D[cols].to_numpy(np.float32))
        if self.anchored:
            p = p + D["AQI"].to_numpy(float)
        return np.clip(p, 0, 500)


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------
CAT_ORDER = ["Good", "Satisfactory", "Moderate", "Poor", "Very Poor", "Severe"]


def metrics(y, p):
    y, p = np.asarray(y, float), np.asarray(p, float)
    cy, cp = aqi_category(y), aqi_category(p)
    alert_y, alert_p = y > 100, p > 100            # Moderate or worse: risk for sensitive groups
    tp = (alert_y & alert_p).sum()
    prec = tp / max(alert_p.sum(), 1)
    rec = tp / max(alert_y.sum(), 1)
    return {
        "MAE": mean_absolute_error(y, p),
        "RMSE": float(np.sqrt(mean_squared_error(y, p))),
        "R2": r2_score(y, p),
        "Cat_Acc": float((cy == cp).mean()),
        "Alert_F1": float(2 * prec * rec / max(prec + rec, 1e-9)),
    }
