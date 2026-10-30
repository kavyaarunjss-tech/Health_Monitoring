"""Latest 15-minute readings from the OpenAQ v3 API (fills the lag of the S3 archive).

Needs OPENAQ_API_KEY in the project's .env file. Free-tier limit is 60 requests/minute, so the
script pauses between calls: 12 sensors x 8 stations = 96 calls, about 2 minutes per update.

Which sensor? Each location lists duplicate sensors per pollutant (e.g. two pm25 sensors). We use the
same sensor ids as the S3 archive (read from data/archive_cache), so the live and archive data match.

Output has the same wide 15-minute format as data/raw, so it goes through aq_clean.py unchanged.
(API hourly values use a different hour convention from aq_clean.py, so we do not use /hours.)

Usage (project root, aqi env):
    python backend/fetch_openaq_api.py --since 2026-10-08
Output: data/live/api_15min_<id>.csv   (datetimeLocal = period end, same as the archive's datetime)
"""
import argparse
import datetime as dt
import glob
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "archive_cache"
OUT = ROOT / "data" / "live"
STATIONS = [6975, 6984, 6973, 6954, 10902, 7289, 10909, 11582]
API = "https://api.openaq.org/v3"
PAUSE = 1.1  # seconds between calls -> < 60 per minute


def read_key():
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("OPENAQ_API_KEY="):
            key = line.split("=", 1)[1].strip().strip('"')
            if key and key != "paste_your_key_here":
                return key
    raise SystemExit("OPENAQ_API_KEY is missing in .env")


def archive_sensors(location_id):
    """{parameter: sensor_id} used by the S3 archive for this station (most common id in the last 7 cached days;
    a single day can lack a parameter)."""
    files = sorted(glob.glob(str(CACHE / str(location_id) / "*.csv.gz")))
    if not files:
        raise SystemExit(f"no archive cache for {location_id}; run fetch_openaq_archive.py first")
    d = pd.concat([pd.read_csv(f) for f in files[-7:]])
    return d.groupby("parameter")["sensors_id"].agg(lambda s: s.mode().iloc[0]).to_dict()


def get(session, url, **params):
    """GET with retries: rate limit (429) -> wait 30 s; OpenAQ server errors (5xx) or a dropped connection -> wait 5, 10, 20, 30 s.
    A 4xx other than 429 (e.g. a bad key) is not retried."""
    waits = [5, 10, 20, 30]
    last = None
    for attempt in range(6):
        try:
            r = session.get(url, params=params, timeout=60)
        except requests.RequestException as e:          # timeout / connection reset
            last = f"connection problem ({e.__class__.__name__})"
        else:
            if r.status_code == 429:  # rate limit: wait for the window to reset
                last = "rate limit (429)"
                time.sleep(30)
                continue
            if r.status_code >= 500:                     # temporary OpenAQ server error
                last = f"OpenAQ server error {r.status_code}"
            else:
                r.raise_for_status()
                time.sleep(PAUSE)
                return r.json()
        if attempt < len(waits):
            print(f"   {last}; retrying in {waits[attempt]} s ...", flush=True)
            time.sleep(waits[attempt])
    raise RuntimeError(f"{last} after several retries: {url}")


def sensor_readings(session, sensor_id, since):
    rows, page = [], 1
    while True:
        j = get(session, f"{API}/sensors/{sensor_id}/measurements", datetime_from=since.isoformat(),
                limit=1000, page=page)
        rows += [(x["period"]["datetimeTo"]["utc"], x["value"]) for x in j["results"]]
        if len(j["results"]) < 1000:
            return rows
        page += 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", type=dt.date.fromisoformat,
                    default=dt.date.today() - dt.timedelta(days=3))
    ap.add_argument("--stations", nargs="*", type=int, default=STATIONS)
    a = ap.parse_args()
    since = dt.datetime.combine(a.since, dt.time(), tzinfo=dt.timezone.utc)
    OUT.mkdir(parents=True, exist_ok=True)
    s = requests.Session()
    s.headers["X-API-Key"] = read_key()
    skipped = []
    for lid in a.stations:
        cols = {}
        for param, sid in archive_sensors(lid).items():
            try:
                rows = sensor_readings(s, int(sid), since)
            except RuntimeError as e:                    # one sensor keeps failing: skip it, do not stop the whole update
                print(f"   WARNING {lid} {param} (sensor {sid}) skipped: {e}", flush=True)
                skipped.append(f"{lid} {param}")
                continue
            if rows:
                df = pd.DataFrame(rows, columns=["t", "value"]).drop_duplicates("t")
                df["t"] = pd.to_datetime(df["t"], utc=True).dt.tz_convert("Asia/Kolkata")
                cols[param] = df.set_index("t")["value"]
        if not cols:                                     # nothing new for this station: keep its previous file
            print(f"{lid}: no readings fetched; previous file kept")
            continue
        wide = pd.DataFrame(cols).sort_index()
        wide.index.name = "datetimeLocal"
        wide.insert(0, "location_id", lid)
        wide.to_csv(OUT / f"api_15min_{lid}.csv")
        print(f"{lid}: {len(wide)} readings, {wide.index.min()} -> {wide.index.max()}")
    if skipped:
        print(f"Done with {len(skipped)} sensor(s) skipped after retries ({', '.join(skipped)}); "
              "run the update again later to fill them in.")


if __name__ == "__main__":
    main()
