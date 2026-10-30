"""
Step 1 - Clean hourly dataset + CPCB AQI with validity rules.

Input : raw 15-minute station files (OpenAQ/KSPCB export, wide format)
Output: one hourly table for all stations with
        - cleaned hourly concentrations (gaps left as NaN, only gaps <= 3 h interpolated)
        - CPCB running averages (24 h for PM2.5/PM10/NO2/SO2, 8 h for O3/CO)
        - sub-indices, AQI (NaN when CPCB minimum-data rules are not met), category
        - QC flags: share of real readings, interpolated hours
"""
import numpy as np
import pandas as pd

POLLUTANTS = ["pm25", "pm10", "no2", "so2", "o3", "co"]          # used in AQI
OTHER_GAS = ["no", "nox"]
MET = ["temperature", "relativehumidity", "wind_speed", "wind_direction"]
ALL_VARS = POLLUTANTS + OTHER_GAS + MET

SENTINELS = [999.99, -99.99, 9999, -999, 999, -9999]

# CPCB breakpoints. The top band ("Severe", 401-500) is given a finite upper
# concentration so the sub-index keeps rising above 400 (capped at 500) instead
# of being stuck at exactly 400.
BREAKPOINTS = {
    "pm25": [(0, 30, 0, 50), (30, 60, 50, 100), (60, 90, 100, 200), (90, 120, 200, 300), (120, 250, 300, 400), (250, 380, 400, 500)],
    "pm10": [(0, 50, 0, 50), (50, 100, 50, 100), (100, 250, 100, 200), (250, 350, 200, 300), (350, 430, 300, 400), (430, 510, 400, 500)],
    "no2":  [(0, 40, 0, 50), (40, 80, 50, 100), (80, 180, 100, 200), (180, 280, 200, 300), (280, 400, 300, 400), (400, 520, 400, 500)],
    "so2":  [(0, 40, 0, 50), (40, 80, 50, 100), (80, 380, 100, 200), (380, 800, 200, 300), (800, 1600, 300, 400), (1600, 2400, 400, 500)],
    "o3":   [(0, 50, 0, 50), (50, 100, 50, 100), (100, 168, 100, 200), (168, 208, 200, 300), (208, 748, 300, 400), (748, 1000, 400, 500)],
    "co":   [(0, 1.0, 0, 50), (1.0, 2.0, 50, 100), (2.0, 10.0, 100, 200), (10.0, 17.0, 200, 300), (17.0, 34.0, 300, 400), (34.0, 51.0, 400, 500)],
}
CATEGORIES = [(50, "Good"), (100, "Satisfactory"), (200, "Moderate"), (300, "Poor"), (400, "Very Poor"), (np.inf, "Severe")]


def subindex(conc, pollutant):
    """Vectorised CPCB sub-index (linear interpolation inside each band)."""
    conc = np.asarray(conc, dtype=float)
    out = np.full(conc.shape, np.nan)
    for blo, bhi, ilo, ihi in BREAKPOINTS[pollutant]:
        m = (conc >= blo) & (conc <= bhi) & np.isnan(out)
        out[m] = ilo + (ihi - ilo) / (bhi - blo) * (conc[m] - blo)
    top = BREAKPOINTS[pollutant][-1]
    out[conc > top[1]] = 500.0
    return out


def aqi_category(aqi):
    aqi = np.asarray(aqi, dtype=float)
    out = np.full(aqi.shape, None, dtype=object)
    lo = -np.inf
    for hi, name in CATEGORIES:
        out[(aqi > lo) & (aqi <= hi)] = name
        lo = hi
    return out


def aqi_from_averages(avgs):
    """avgs: dict pollutant -> array of CPCB-averaged concentration.
    Returns (AQI, subindex dict). AQI = max sub-index, valid only if >=3
    pollutants available and at least one of PM2.5/PM10 (CPCB rule)."""
    si = {p: subindex(avgs[p], p) for p in POLLUTANTS}
    S = np.column_stack([si[p] for p in POLLUTANTS])
    n_avail = np.isfinite(S).sum(1)
    pm_ok = np.isfinite(si["pm25"]) | np.isfinite(si["pm10"])
    with np.errstate(all="ignore"):
        aqi = np.nanmax(np.where(np.isfinite(S), S, -np.inf), axis=1)
    aqi[(n_avail < 3) | ~pm_ok] = np.nan
    return aqi, si


def _qc_15min(df):
    """Physical / sentinel / spike checks on 15-minute data."""
    df = df.copy()
    log = {}
    for c in ALL_VARS:
        if c not in df:
            df[c] = np.nan
            continue
        x = pd.to_numeric(df[c], errors="coerce")
        bad = x.isin(SENTINELS) | (x.abs() >= 999)
        if c in ("pm25", "pm10"):
            bad |= x <= 0
        elif c in POLLUTANTS + OTHER_GAS:
            bad |= x < 0
        elif c == "relativehumidity":
            bad |= (x <= 0) | (x > 100)
        elif c == "temperature":
            bad |= (x <= 0) | (x > 50)
        elif c == "wind_speed":
            bad |= (x < 0) | (x > 40)
        elif c == "wind_direction":
            bad |= (x < 0) | (x > 360)
        log[c] = {"sentinel_or_range": int(bad.sum())}
        df[c] = x.mask(bad)
    # Spike filter (Hampel-style) for pollutants: a reading far above the
    # local 3-hour median is treated as an instrument glitch.
    for c in POLLUTANTS + OTHER_GAS:
        x = df[c]
        med = x.rolling("3h", center=True, min_periods=4).median()
        # robust spread over a 7-day window, so clusters of glitches cannot inflate it
        mad = (x - med).abs().rolling("7D", center=True, min_periods=50).median()
        floor = {"co": 1.0}.get(c, 30.0)
        spike = (x - med) > np.maximum(8 * 1.4826 * mad, floor) + 2 * med
        # isolated readings with no neighbours and absurd level
        lone = med.isna() & (x > {"co": 10}.get(c, 500))
        s = spike.fillna(False) | lone
        log[c]["spike"] = int(s.sum())
        df[c] = x.mask(s)
    # Stuck-high sensor: the same high value repeated for >= 3 hours
    # (these exports repeat hourly values 4x, so <= 4 repeats is normal)
    for c in ["pm25", "pm10"]:
        x = df[c]
        run = (x != x.shift()).cumsum()
        run_len = x.groupby(run).transform("size")
        base = x.rolling("30D", min_periods=100).median()
        stuck = (run_len >= 12) & (x > 4 * base) & (x > 150)
        log[c]["stuck_high"] = int(stuck.sum())
        df.loc[stuck, c] = np.nan
    # PM2.5 cannot physically exceed PM10 by a wide margin
    bad_ratio = (df["pm25"] > 1.5 * df["pm10"] + 20)
    log["pm25"]["pm25>pm10"] = int(bad_ratio.sum())
    df.loc[bad_ratio, "pm25"] = np.nan
    # Error-code pattern seen in these exports: PM2.5 ~ 600-800 exactly when the
    # PM10 channel drops out. Very high PM2.5 with no PM10 reading is rejected.
    lone_pm = (df["pm25"] > 250) & df["pm10"].isna()
    log["pm25"]["high_pm25_no_pm10"] = int(lone_pm.sum())
    df.loc[lone_pm, "pm25"] = np.nan
    return df, log


def _read_any(path):
    """The raw exports are CSV text even when named .xls; fall back to Excel if needed."""
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.read_excel(path)


def clean_station(raw_path, station, max_gap_h=3):
    raw = _read_any(raw_path)
    raw["t"] = pd.to_datetime(raw["datetimeLocal"].astype(str).str[:19])
    keep = [c for c in ALL_VARS if c in raw.columns]
    raw = raw[["t"] + keep].groupby("t").mean().sort_index()     # duplicate timestamps -> mean
    q, log = _qc_15min(raw)

    # Hourly mean; an hour needs >= 2 valid 15-min readings
    hourly = q.resample("1h").mean()
    counts = q.resample("1h").count()
    hourly = hourly.mask(counts < 2)
    # wind direction: vector average
    if q["wind_direction"].notna().any():
        rad = np.deg2rad(q["wind_direction"])
        u = (-q["wind_speed"] * np.sin(rad)).resample("1h").mean()
        v = (-q["wind_speed"] * np.cos(rad)).resample("1h").mean()
    else:
        u = v = pd.Series(np.nan, index=hourly.index)
    hourly["wind_u"], hourly["wind_v"] = u, v
    hourly = hourly.asfreq("1h")

    real = hourly[POLLUTANTS].notna()
    # Interpolate only short gaps (<= max_gap_h); longer gaps stay missing
    num = hourly.columns.drop("wind_direction")
    filled = hourly[num].interpolate(method="time", limit=max_gap_h, limit_area="inside")
    # interpolate() with limit fills the first N hours of long gaps too -> undo that
    for c in num:
        isna = hourly[c].isna()
        run_id = (isna != isna.shift()).cumsum()
        run_len = isna.groupby(run_id).transform("sum")
        filled.loc[isna & (run_len > max_gap_h), c] = np.nan
    hourly[num] = filled

    # CPCB running averages (min 16 of 24 h; 6 of 8 h)
    avgs = {}
    for p in ["pm25", "pm10", "no2", "so2"]:
        avgs[p] = hourly[p].rolling(24, min_periods=16).mean()
    for p in ["o3", "co"]:
        avgs[p] = hourly[p].rolling(8, min_periods=6).mean()
    aqi, si = aqi_from_averages({p: avgs[p].to_numpy() for p in POLLUTANTS})

    out = hourly.copy()
    for p in POLLUTANTS:
        out[f"{p}_avg"] = avgs[p]
        out[f"{p}_si"] = si[p]
    out["AQI"] = np.round(aqi)
    S = out[[f"{p}_si" for p in POLLUTANTS]].to_numpy()
    idx = np.argmax(np.where(np.isfinite(S), S, -1), axis=1)
    out["dominant"] = np.where(out["AQI"].notna(), np.array(POLLUTANTS, dtype=object)[idx], None)
    out["category"] = aqi_category(out["AQI"])
    out["real_pm"] = (real["pm25"] | real["pm10"]).astype(int)
    out["station"] = station
    out.index.name = "datetime"
    return out.reset_index(), log


# Raw 15-minute file per station (file name without extension; .csv, .xls or .xlsx all work)
RAW_FILES = {
    "chikkaballapura": "Merged_chikkaballapura",
    "chikkamagaluru": "Merged_chikkamagaluru",
    "hebbal": "Merged_hebbal",
    "jayanagar": "converted_jayanagar",
    "madikeri": "Merged_madikeri",
    "mysuru": "Merged_mysuru",
    "ramanagara": "Merged_ramanagara",
    "silkboard": "Merged_silkboard",
}


def build_clean_dataset(raw_dir, files=RAW_FILES):
    import glob, os
    frames, logs = [], {}
    for st, fname in files.items():
        hits = sorted(h for ext in ("csv", "xls", "xlsx")
                      for h in glob.glob(os.path.join(raw_dir, f"*{fname}.{ext}")))
        if not hits:
            raise FileNotFoundError(f"{fname}.csv / .xls / .xlsx not found in {os.path.abspath(raw_dir)}")
        print(f"{st:16s} <- {os.path.basename(hits[0])}")
        df, log = clean_station(hits[0], st)
        frames.append(df)
        logs[st] = log
    return pd.concat(frames, ignore_index=True), logs
