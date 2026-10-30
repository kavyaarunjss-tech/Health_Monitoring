"""One-call retry of the data.gov.in CPCB real-time AQI API (needs DATA_GOV_IN_API_KEY in .env).
It returned HTTP 502 on 2026-10-14. Prints status, fields and a Karnataka sample; never prints the key."""
import json
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
RID = "3b01bcb8-0b14-4abf-b6f2-c1bfd384ba69"
key = next((l.split("=", 1)[1].strip().strip('"') for l in (ROOT / ".env").read_text(encoding="utf-8").splitlines()
            if l.startswith("DATA_GOV_IN_API_KEY=")), "")
if len(key) < 10:
    raise SystemExit("DATA_GOV_IN_API_KEY missing in .env")
t = time.time()
try:
    r = requests.get(f"https://api.data.gov.in/resource/{RID}",
                     params={"api-key": key, "format": "json", "limit": 5, "filters[state]": "Karnataka"}, timeout=150)
except Exception as e:  # noqa: BLE001
    raise SystemExit(f"{type(e).__name__} after {time.time() - t:.0f}s")
print(f"HTTP {r.status_code} in {time.time() - t:.1f}s")
try:
    j = r.json()
    print("fields:", [f.get("id") for f in j.get("field", [])])
    print("total:", j.get("total"), "| updated:", j.get("updated_date"))
    print(json.dumps((j.get("records") or [None])[0], indent=1)[:600])
except ValueError:
    print("non-JSON body:", r.text[:200])
