"""One-call latency test: Silk Board (WAQI station @11293) vs OpenAQ (location 6975).
Needs WAQI_TOKEN and OPENAQ_API_KEY in .env. Prints how old the newest reading is in each source.
Note: WAQI 'iaqi' values are AQI sub-indices (US EPA style), not concentrations, so we compare TIMES,
not values. Run it at different hours of the day and compare."""
import datetime as dt
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def env(name):
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith(name + "="):
            v = line.split("=", 1)[1].strip().strip('"')
            if v and not v.startswith("paste"):
                return v
    raise SystemExit(f"{name} is missing in .env")


now = dt.datetime.now(IST)
print("now (IST):", now.strftime("%Y-%m-%d %H:%M"))

w = requests.get("https://api.waqi.info/feed/@11293/", params={"token": env("WAQI_TOKEN")}, timeout=30).json()
if w.get("status") != "ok":
    raise SystemExit(f"WAQI error: {w}")
d = w["data"]
t = dt.datetime.fromisoformat(d["time"]["iso"])
print(f"WAQI    : {d['city']['name']}  newest {t:%Y-%m-%d %H:%M}  age {(now - t).total_seconds() / 3600:.1f} h  "
      f"AQI {d.get('aqi')}  dominant {d.get('dominentpol')}")
print("          pollutants reported:", sorted(d.get("iaqi", {}).keys()))
print("          credits:", [a.get("name") for a in d.get("attributions", [])])

o = requests.get("https://api.openaq.org/v3/locations/6975", headers={"X-API-Key": env("OPENAQ_API_KEY")},
                 timeout=30).json()["results"][0]
t2 = dt.datetime.fromisoformat(o["datetimeLast"]["local"])
print(f"OpenAQ  : {o['name']}  newest {t2:%Y-%m-%d %H:%M}  age {(now - t2).total_seconds() / 3600:.1f} h")
print(f"WAQI is {(t - t2).total_seconds() / 3600:+.1f} h ahead of OpenAQ")
