"""Build the live dataset: raw (before 1 Jul 2026) + S3 archive (from 1 Jul) + API tail -> aq_clean.py -> SQLite.

Steps (run the two fetch scripts first):
  1. per station, stitch the three 15-minute sources into one raw-format file (data/live/combined/)
  2. run model/aq_clean.py unchanged on those files (QC, hourly means, CPCB AQI)
  3. save to SQLite data/aqi.db: tables hourly (clean data + AQI), weather_hist, weather_fcst

Usage (project root, aqi env):  python backend/build_dataset.py
"""
import sqlite3
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model"))
import aq_clean  # noqa: E402

CUTOFF = pd.Timestamp("2026-07-01 00:00:00")  # local time: raw before, archive from here on
IDS = {"silkboard": 6975, "hebbal": 6984, "jayanagar": 6973, "chikkaballapura": 6954,
       "chikkamagaluru": 10902, "mysuru": 7289, "ramanagara": 10909, "madikeri": 11582}
LIVE = ROOT / "data" / "live"
COMBINED = LIVE / "combined"
DB = ROOT / "data" / "aqi.db"


def local_naive(df):
    df = df.copy()
    df["t"] = pd.to_datetime(df["datetimeLocal"].astype(str).str[:19])  # same as aq_clean (local clock)
    return df


def stitch(station, lid):
    raw = local_naive(pd.read_csv(ROOT / "data" / "raw" / f"{aq_clean.RAW_FILES[station]}.csv"))
    raw = raw[raw["t"] < CUTOFF]
    arch = local_naive(pd.read_csv(LIVE / f"{lid}_wide.csv"))
    arch = arch[arch["t"] >= CUTOFF]
    parts = [raw, arch]
    api_file = LIVE / f"api_15min_{lid}.csv"
    if api_file.exists():
        api = local_naive(pd.read_csv(api_file))
        api = api[api["t"] > arch["t"].max()]          # only readings newer than the archive
        parts.append(api)
    cols = ["datetimeLocal"] + [c for c in aq_clean.ALL_VARS]
    out = pd.concat([p.reindex(columns=cols) for p in parts], ignore_index=True)
    out = out.assign(_t=pd.to_datetime(out["datetimeLocal"].astype(str).str[:19])).sort_values("_t")
    out = out.drop(columns="_t")
    COMBINED.mkdir(parents=True, exist_ok=True)
    out.to_csv(COMBINED / f"{aq_clean.RAW_FILES[station]}.csv", index=False)
    return len(raw), len(arch), len(parts[2]) if len(parts) > 2 else 0


def main():
    for st, lid in IDS.items():
        n = stitch(st, lid)
        print(f"{st:16s} rows: raw={n[0]} archive={n[1]} api_tail={n[2]}")
    clean, logs = aq_clean.build_clean_dataset(str(COMBINED))
    with sqlite3.connect(DB, timeout=60) as con:
        con.execute("PRAGMA journal_mode=WAL")           # readers (the web server) are not blocked while tables are rewritten
        clean.to_sql("hourly", con, if_exists="replace", index=False)
        for kind in ("hist", "fcst"):
            frames = []
            for lid in IDS.values():
                w = pd.read_csv(LIVE / f"weather_{kind}_{lid}.csv")
                w["datetimeLocal"] = w["datetimeLocal"].astype(str).str[:19]  # local clock, like hourly
                w.insert(0, "location_id", lid)
                frames.append(w)
            pd.concat(frames).to_sql(f"weather_{kind}", con, if_exists="replace", index=False)
        con.execute("CREATE INDEX IF NOT EXISTS ix_hourly ON hourly(station, datetime)")
    print(f"\nsaved {DB} : hourly rows = {len(clean)}")
    last = clean.dropna(subset=["AQI"]).groupby("station")["datetime"].max()
    print("newest valid AQI per station:\n" + last.to_string())


if __name__ == "__main__":
    main()
