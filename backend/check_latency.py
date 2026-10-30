"""How old is the newest OpenAQ reading at each station? (8 small calls, ~20 s)
Run it at different hours of the day to learn when new data arrives."""
import datetime as dt
import time
import requests
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
NAMES = {6975: "Silk Board", 6984: "Hebbal", 6973: "Jayanagar", 6954: "Chikkaballapur",
         10902: "Chikkamagaluru", 7289: "Mysuru", 10909: "Ramanagara", 11582: "Madikeri"}


def key():
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("OPENAQ_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"')
    raise SystemExit("OPENAQ_API_KEY missing in .env")


now = dt.datetime.now(IST)
print("now (IST):", now.strftime("%Y-%m-%d %H:%M"))
for lid, name in NAMES.items():
    r = requests.get(f"https://api.openaq.org/v3/locations/{lid}", headers={"X-API-Key": key()}, timeout=30)
    last = dt.datetime.fromisoformat(r.json()["results"][0]["datetimeLast"]["local"])
    print(f"{name:16s} newest {last:%Y-%m-%d %H:%M}   age {(now - last).total_seconds() / 3600:5.1f} h")
    time.sleep(1.1)
