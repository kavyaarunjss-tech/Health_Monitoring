"""Tests for the Pollutants tab data and pollutant display names.

1. The AVERAGE concentration shown next to each bar must reproduce the shown SUB-INDEX through the CPCB breakpoints (model/aq_clean.subindex).
   (Found 2026-10-17: the tab showed the HOURLY PM2.5 92.9 next to sub-index 250; CPCB gives ~210 for 92.9, and 250 comes from the 24 h average 104.86.)
2. The displayed AQI is the maximum displayed sub-index (CPCB rule), so the 'main pollutant' bar always matches the AQI.
3. Display names: PM2.5, PM10, NO2, SO2, O3, CO (with subscripts) everywhere, never 'PM25' (e-mails included).

usage (project root, aqi env):  python backend\\test_pollutants.py
"""
import os
import random
import sqlite3
import sys
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="aqi_polltest_"))
os.environ.update({"AQI_EMAIL_FAKE": "1", "AQI_RATE_FILE": str(TMP / "rate.json"), "AQI_PROFILE_FILE": str(TMP / "profile.json")})
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "model"))
import aq_clean  # noqa: E402
import advice as adv  # noqa: E402
import app as appmod  # noqa: E402
import live_api  # noqa: E402
import notify_email as ne  # noqa: E402

failures = []


def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  {extra}" if extra else ""))
    if not cond:
        failures.append(name)


def reproduce(key, avg):
    return float(aq_clean.subindex([avg], key)[0])


def audit(pollutants, now_aqi, where, stats, bad):
    for p in pollutants:
        if p["avg"] is None or p["si"] is None:
            continue
        r = reproduce(p["key"], p["avg"])
        stats["n"] += 1
        stats["maxdiff"] = max(stats["maxdiff"], abs(r - p["si"]))
        if abs(r - p["si"]) > 1.0:
            bad.append((where, p["key"], p["avg"], p["si"], round(r, 1)))
        if p["value"] is not None and abs(p["value"] - p["avg"]) > 1e-9:
            stats["avg_differs_from_hourly"] += 1
    sis = [p["si"] for p in pollutants if p["si"] is not None]
    if sis and now_aqi is not None and len(sis) >= 3:
        stats["aqi_rows"] += 1
        if abs(max(sis) - now_aqi) > 1.0:
            stats["aqi_mismatch"].append((where, max(sis), now_aqi))


# ---- 1/2. replay: a random sample of observed hours of both periods ---------------------------------------------------------------
random.seed(7)
con = sqlite3.connect(ROOT / "data" / "replay.db")
rows = con.execute("SELECT station, datetime FROM replay_obs WHERE AQI IS NOT NULL AND datetime BETWEEN '2026-04-17 07:00:00' AND '2026-07-21 23:00:00'").fetchall()
sample = random.sample(rows, 400)
stats = {"n": 0, "maxdiff": 0.0, "avg_differs_from_hourly": 0, "aqi_rows": 0, "aqi_mismatch": []}
bad = []
for st, t in sample:
    s = appmod.state("validation" if t < "2026-05-29 14:00:00" else "test", st, t)
    if s["pollutants"]:
        audit(s["pollutants"], s["now"]["aqi"] if s["now"] else None, (st, t), stats, bad)
check("T1 replay: the shown average reproduces the shown sub-index (CPCB breakpoints) for every pollutant, 400 random hours",
      not bad and stats["n"] > 1500, f"({stats['n']} pollutant values, max difference {stats['maxdiff']:.2f}, failures {bad[:2]})")
check("T2 replay: the AQI equals the highest shown sub-index (main-pollutant bar matches the AQI)", not stats["aqi_mismatch"] and stats["aqi_rows"] > 300,
      f"({stats['aqi_rows']} hours, mismatches {stats['aqi_mismatch'][:2]})")
check("T3 the shown average is genuinely a different number from the hourly value (the earlier bug is visible in the data)",
      stats["avg_differs_from_hourly"] > 0.5 * stats["n"], f"({stats['avg_differs_from_hourly']} of {stats['n']} differ)")

# the exact case from the bug report
s = appmod.state("validation", "silkboard", "2026-04-24 01:00:00")
pm25 = next(p for p in s["pollutants"] if p["key"] == "pm25")
check("T4 Silk Board 24 Apr 02:00: PM2.5 24 h average ~105 gives sub-index 250; the hourly 92.9 would have given ~210 (the old mismatch)",
      abs(pm25["avg"] - 104.86) < 0.01 and pm25["si"] == 250 and abs(reproduce("pm25", pm25["value"]) - 209.7) < 0.5 and pm25["value"] == 92.9,
      f"(avg {pm25['avg']} -> {pm25['si']}; hourly {pm25['value']} would give {reproduce('pm25', pm25['value']):.1f})")

# ---- live: every station's last observation -------------------------------------------------------------------------------------
stats = {"n": 0, "maxdiff": 0.0, "avg_differs_from_hourly": 0, "aqi_rows": 0, "aqi_mismatch": []}
bad = []
for st in live_api.STATIONS:
    s = live_api.state(st)
    if s.get("pollutants"):
        audit(s["pollutants"], s.get("last_aqi"), (st, "live"), stats, bad)
check("T5 live: the shown average reproduces the shown sub-index for every station's last observation", not bad and stats["n"] > 20,
      f"({stats['n']} values, max difference {stats['maxdiff']:.2f}, failures {bad[:2]})")
check("T6 live: the AQI equals the highest shown sub-index", not stats["aqi_mismatch"], f"({stats['aqi_mismatch'][:2]})")

# ---- 3. display names -----------------------------------------------------------------------------------------------------------
check("N1 display names", [adv.pname(k) for k in ("pm25", "pm10", "no2", "so2", "o3", "co")] == ["PM2.5", "PM10", "NO₂", "SO₂", "O₃", "CO"])
fc = {"aqi": 150, "category": "Moderate", "dominant": "pm25", "range_low": 120, "range_high": 190, "category_low": "Moderate", "category_high": "Moderate",
      "tier": "high", "horizon": 6, "target_end": "2026-04-24 08:00"}
subj, body = ne.compose_alert("replay", "Silk Board", "likely", fc, {"groups": ["lung"], "alert_from": 101}, "issued")
check("N2 e-mails say 'mainly PM2.5', never 'PM25'", "mainly PM2.5" in body and "PM25" not in subj + body)
labels = [p["label"] for p in appmod.state("validation", "silkboard", "2026-04-24 01:00:00")["pollutants"]]
check("N3 pollutant labels in the API", labels == ["PM2.5", "PM10", "NO₂", "SO₂", "O₃", "CO"], f"({labels})")

print("\nALL PASSED" if not failures else f"\n{len(failures)} FAILED: {failures}")
sys.exit(1 if failures else 0)
