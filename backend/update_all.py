"""One command to refresh everything: archive -> API tail -> weather -> clean dataset (SQLite).

Usage (project root, aqi env):
    python backend/update_all.py                # normal update (last 10 days)
    python backend/update_all.py --days 3       # shorter window
    python backend/update_all.py --quick        # hourly job: API tail (7 days) + forecast weather + rebuild + live forecasts
Takes ~4-6 minutes, almost all of it in the OpenAQ API step (96 calls at 60/min).
If a data step fails the later steps are skipped and the database keeps its previous content; live mode then simply shows older data
with a "data is N hours old" banner (the age is computed from the data itself).
"""
import argparse
import datetime as dt
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run(name, args):
    t = time.time()
    print(f"\n=== {name} ===", flush=True)
    r = subprocess.run([sys.executable, str(HERE / args[0]), *args[1:]])
    if r.returncode != 0:
        raise SystemExit(f"step '{name}' failed (exit {r.returncode}); later steps skipped")
    print(f"--- {name} done in {time.time() - t:.0f} s", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=10)
    ap.add_argument("--quick", action="store_true", help="hourly update: skip the S3 archive and weather history (daily job does those)")
    a = ap.parse_args()
    today = dt.date.today()
    since = (today - dt.timedelta(days=a.days)).isoformat()
    if a.quick:
        # hourly: the API tail must reach back past the archive's newest day (the archive lags ~3 days); 7 days of 15-min readings still fit in
        # ONE page per sensor, so this costs the same 96 calls as a shorter window
        run("OpenAQ API tail", ["fetch_openaq_api.py", "--since", (today - dt.timedelta(days=7)).isoformat()])
        run("Open-Meteo forecast", ["fetch_weather.py", "--forecast-only"])
    else:
        run("S3 archive", ["fetch_openaq_archive.py", "--start", since, "--end", today.isoformat()])
        # the API tail must start before the archive's newest day so the two sources overlap
        run("OpenAQ API tail", ["fetch_openaq_api.py", "--since", (today - dt.timedelta(days=4)).isoformat()])
        run("Open-Meteo weather", ["fetch_weather.py", "--start", "2025-02-19", "--end", today.isoformat()])
    run("Build clean dataset", ["build_dataset.py"])
    run("Live forecasts (model if trained, else persistence fallback)", ["forecast_live.py"])
    print("\nAll done.")


if __name__ == "__main__":
    main()
