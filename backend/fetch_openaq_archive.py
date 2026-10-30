"""Download KSPCB station data from the public OpenAQ S3 archive and pivot it to the wide
format used in data/raw (one row per timestamp, one column per pollutant).

Usage (from the project root):
    python backend/fetch_openaq_archive.py --start 2026-07-01 --end 2026-10-14
    python backend/fetch_openaq_archive.py --start 2026-07-01 --end 2026-10-14 --stations 6975

Daily files are cached in data/archive_cache/<location_id>/, so re-running only downloads
days that are missing. Output: data/live/<location_id>_wide.csv
"""
import argparse
import datetime as dt
import gzip
import io
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd
import requests

BUCKET = "https://openaq-data-archive.s3.amazonaws.com"
STATIONS = {6975: "silkboard", 6984: "hebbal", 6973: "jayanagar", 6954: "chikkaballapura",
            10902: "chikkamagaluru", 7289: "mysuru", 10909: "ramanagara", 11582: "madikeri"}
# columns of data/raw (after the identifying ones)
WIDE_COLS = ["co", "no", "no2", "nox", "o3", "pm10", "pm25", "relativehumidity", "so2",
             "temperature", "wind_direction", "wind_speed"]
ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "archive_cache"
OUT = ROOT / "data" / "live"


def list_keys(location_id, year, month):
    """List archive files for one station-month (the S3 listing is a public XML page)."""
    prefix = f"records/csv.gz/locationid={location_id}/year={year}/month={month:02d}/"
    keys, token = [], None
    while True:
        params = {"list-type": "2", "prefix": prefix}
        if token:
            params["continuation-token"] = token
        r = requests.get(BUCKET, params=params, timeout=30)
        r.raise_for_status()
        ns = {"s": "http://s3.amazonaws.com/doc/2006-03-01/"}
        root = ET.fromstring(r.text)
        keys += [k.text for k in root.findall("s:Contents/s:Key", ns)]
        if root.findtext("s:IsTruncated", namespaces=ns) != "true":
            return keys
        token = root.findtext("s:NextContinuationToken", namespaces=ns)


def months_between(start, end):
    d = dt.date(start.year, start.month, 1)
    while d <= end:
        yield d.year, d.month
        d = (d.replace(day=28) + dt.timedelta(days=4)).replace(day=1)


def download_station(location_id, start, end):
    folder = CACHE / str(location_id)
    folder.mkdir(parents=True, exist_ok=True)
    new = 0
    for y, m in months_between(start, end):
        for key in list_keys(location_id, y, m):
            day = re.search(r"-(\d{8})\.csv\.gz$", key)
            if not day:
                continue
            d = dt.datetime.strptime(day.group(1), "%Y%m%d").date()
            if not (start <= d <= end):
                continue
            target = folder / Path(key).name
            # re-download the newest 3 days: the archive may still be filling them
            if target.exists() and d < end - dt.timedelta(days=3):
                continue
            r = requests.get(f"{BUCKET}/{key}", timeout=60)
            r.raise_for_status()
            target.write_bytes(r.content)
            new += 1
            time.sleep(0.05)
    return new


def build_wide(location_id):
    """Read all cached day files of a station and pivot to wide format."""
    frames = []
    for f in sorted((CACHE / str(location_id)).glob("*.csv.gz")):
        with gzip.open(f, "rt", encoding="utf-8") as fh:
            frames.append(pd.read_csv(fh, dtype={"value": "float64"}))
    if not frames:
        return None
    long = pd.concat(frames, ignore_index=True)
    long["datetimeLocal"] = pd.to_datetime(long["datetime"], utc=True).dt.tz_convert("Asia/Kolkata")
    wide = (long.pivot_table(index="datetimeLocal", columns="parameter", values="value", aggfunc="mean")
            .reindex(columns=WIDE_COLS).reset_index().sort_values("datetimeLocal"))
    wide.insert(1, "location_id", location_id)
    return wide


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True, type=dt.date.fromisoformat)
    ap.add_argument("--end", default=dt.date.today().isoformat(), type=dt.date.fromisoformat)
    ap.add_argument("--stations", nargs="*", type=int, default=list(STATIONS))
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    for lid in a.stations:
        n = download_station(lid, a.start, a.end)
        wide = build_wide(lid)
        if wide is None:
            print(f"{lid} {STATIONS[lid]}: no data found")
            continue
        wide.to_csv(OUT / f"{lid}_wide.csv", index=False)
        print(f"{lid} {STATIONS[lid]}: {n} new day files, {len(wide)} rows, "
              f"{wide['datetimeLocal'].min()} -> {wide['datetimeLocal'].max()}")


if __name__ == "__main__":
    main()
