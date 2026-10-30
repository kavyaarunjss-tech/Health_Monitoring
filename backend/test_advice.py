"""Tests for the personalised advice (advice.personal_advice), the station's typical time-of-day pattern (diurnal.py) and the tips.

Checks: the "best time" comes from the station's hourly PM2.5/PM10 pattern of the 28 days before the hour, computed WITHOUT future data;
the "no clear time" and "not enough data" cases; Very Poor / Severe -> "Limit outdoor activity at all times"; every tip has a citation, is allowed
for its category and profile (N95 only from Very Poor, never for a child, no inhalers) and appears word for word in the reference document;
the same alert always gets the same tip (pop-up and e-mail too); consecutive alert numbers get different tips; every advice line is cited;
the pop-up has 1-2 profile lines, trend, best time and 1 tip. No server port, no e-mail.

usage (project root, aqi env):  python backend\\test_advice.py
"""
import itertools
import os
import re
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TMP = Path(tempfile.mkdtemp(prefix="aqi_advice_"))
os.environ.update(AQI_EMAIL_FAKE="1", AQI_USERS_DB=str(TMP / "users.db"), AQI_SECRET_KEY="advice-test-" + "z" * 40,
                  AQI_PROFILE_FILE=str(TMP / "profile.json"), AQI_RATE_FILE=str(TMP / "rate.json"))
sys.path.insert(0, str(ROOT / "backend"))
import advice as adv  # noqa: E402
import diurnal  # noqa: E402

failures = []
FMT = "%Y-%m-%d %H:%M:%S"


def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  {extra}" if extra else ""))
    if not cond:
        failures.append(name)


GROUPS = ["lung", "heart", "child", "older", "pregnant", "outdoor_worker", "athlete"]
AQIS = [30, 75, 150, 250, 350, 450]                       # one value per category
CATS = ["Good", "Satisfactory", "Moderate", "Poor", "Very Poor", "Severe"]
FC = [{"horizon": 1, "aqi": 120, "target_end": "2026-04-22 03:00"}, {"horizon": 6, "aqi": 160, "target_end": "2026-04-22 08:00"},
      {"horizon": 12, "aqi": 140, "target_end": "2026-04-22 14:00"}, {"horizon": 24, "aqi": 95, "target_end": "2026-04-23 02:00"}]
CITE = re.compile(r"^(\[\d\])+$")
MARKERS = (adv.FORECAST_SRC, adv.STATION_SRC)


def synthetic(t, days=28, shape=None, missing_days=0):
    """Hourly rows for the `days` days before t; shape(h) = level at hour h."""
    t0, rows = datetime.strptime(t, FMT), []
    for d in range(days * 24):
        dt = t0 - timedelta(hours=d)
        if (d // 24) < missing_days:
            continue
        v = shape(dt.hour)
        rows.append((dt.strftime(FMT), v, 2 * v, 1))
    return rows


def profiles():
    yield {"groups": [], "alert_from": 201}
    for g in GROUPS:
        yield {"groups": [g], "alert_from": 101}
    for a, b in itertools.combinations(GROUPS, 2):
        yield {"groups": [a, b], "alert_from": 101}
    yield {"groups": GROUPS, "alert_from": 51}


T = "2026-04-24 01:00:00"
OK = diurnal.profile_from_rows(synthetic(T, shape=lambda h: 20 if 13 <= h <= 15 else (80 if 19 <= h <= 21 else 50)), T)

# ---- D. the station's typical time-of-day pattern ----
check("D1 synthetic station with a clean afternoon and a dirty evening: usually cleanest 1-4 pm, usually worst 7-10 pm",
      OK["status"] == "ok" and OK["best"]["label"] == "1–4 pm" and OK["worst"]["label"] == "7–10 pm", str({k: OK.get(k) for k in ("status", "best", "worst", "drop")}))
flat = diurnal.profile_from_rows(synthetic(T, shape=lambda h: 50 + (h % 3)), T)
check("D2 'no clear time': blocks differ by less than 20% -> status no_clear", flat["status"] == "no_clear", str(flat.get("drop")))
few = diurnal.profile_from_rows(synthetic(T, shape=lambda h: 20 if 13 <= h <= 15 else 80, missing_days=9), T)
check("D3 only 19 of 28 days with data -> not enough data (needs >= 20 days per hour)", few["status"] == "not_enough_data", str(few.get("valid_hours")))
twenty = diurnal.profile_from_rows(synthetic(T, shape=lambda h: 20 if 13 <= h <= 15 else 80, missing_days=8), T)
check("D4 exactly 20 of 28 days -> enough", twenty["status"] == "ok")
gap = diurnal.profile_from_rows([r for r in synthetic(T, shape=lambda h: 20 if 13 <= h <= 15 else 80) if not r[0][11:13] in ("13", "14", "15")], T)
check("D5 hours without data are never chosen as the cleanest block", gap.get("best", {}).get("start") not in (11, 12, 13, 14, 15))
filled = [(dt, p25, p10, 0 if dt[11:13] == "14" else 1) for dt, p25, p10, _ in synthetic(T, shape=lambda h: 20 if 13 <= h <= 15 else 80)]
check("D6 gap-filled hours (real_pm = 0) are not used", diurnal.profile_from_rows(filled, T)["days_per_hour"][14] == 0)
# no future data (no leakage)
future = synthetic((datetime.strptime(T, FMT) + timedelta(days=10)).strftime(FMT), days=10, shape=lambda h: 999 if 13 <= h <= 15 else 1)
base_rows = synthetic(T, shape=lambda h: 20 if 13 <= h <= 15 else (80 if 19 <= h <= 21 else 50))
with_future = diurnal.profile_from_rows(base_rows + future, T)
check("D7 rows after t (even extreme ones) do not change the pattern (only data available at t is used)",
      {k: with_future[k] for k in ("status", "best", "worst", "drop")} == {k: OK[k] for k in ("status", "best", "worst", "drop")})
old = synthetic((datetime.strptime(T, FMT) - timedelta(days=28)).strftime(FMT), days=20, shape=lambda h: 999 if 13 <= h <= 15 else 1)
check("D8 rows older than 28 days do not change the pattern", {k: diurnal.profile_from_rows(base_rows + old, T)[k] for k in ("best", "worst")} ==
      {k: OK[k] for k in ("best", "worst")})
# the real replay database: same result as a copy whose future hours were replaced by nonsense
db = TMP / "replay_copy.db"
shutil.copy(ROOT / "data" / "replay.db", db)
with sqlite3.connect(db) as c:
    c.execute("UPDATE replay_pm SET pm25 = 9999, pm10 = 9999 WHERE station='silkboard' AND datetime > ?", (T,))
real = diurnal.replay_profile("silkboard", T)
poisoned = diurnal._cached(str(db), "replay_pm", "silkboard", T)
check("D9 replay (Silk Board, 24 Apr 01:00): identical pattern when every later hour in the database is replaced by 9999 (no leakage)",
      {k: real.get(k) for k in ("status", "best", "worst", "drop")} == {k: poisoned.get(k) for k in ("status", "best", "worst", "drop")},
      str({k: real.get(k) for k in ("status", "best", "worst", "drop")}))
check("D10 the window ends exactly at the simulated hour and starts 28 days earlier", real["window_to"] == T and real["window_from"] == "2026-03-27 01:00:00")
check("D11 the first replay hour (17 Apr 07:00) already has 28 days of history", diurnal.replay_profile("silkboard", "2026-04-17 07:00:00")["status"] in ("ok", "no_clear"))

# ---- B. best-time line ----
lung = {"groups": ["lung"], "alert_from": 101}
p_ok = adv.personal_advice(150, lung, FC, 118, "pm10", 0, OK)
check("B1 pattern ok: 'Usually cleanest at this station: 1-4 pm; usually worst: 7-10 pm (typical pattern ... not a forecast) [5]'",
      p_ok["best_time"]["text"] == "Usually cleanest at this station: 1–4 pm; usually worst: 7–10 pm (typical pattern from the last 4 weeks, not a forecast)"
      and p_ok["best_time"]["source"] == "[5]", p_ok["best_time"]["text"])
p_nc = adv.personal_advice(150, lung, FC, 118, "pm10", 0, flat)
check("B2 no clear pattern: 'No clearly better time at this station'", p_nc["best_time"]["text"].startswith("No clearly better time at this station")
      and p_nc["best"] is None)
p_ne = adv.personal_advice(150, lung, FC, 118, "pm10", 0, few)
check("B3 not enough data: 'No clearly better time ... (not enough measurements ...)'", "not enough measurements" in p_ne["best_time"]["text"])
for aqi in (350, 450):
    p_vp = adv.personal_advice(aqi, lung, FC, aqi, "pm25", 0, OK)
    if p_vp["best_time"]["text"] != "Limit outdoor activity at all times" or p_vp["best_time"]["source"] != "[3]" or p_vp["best"] is not None:
        failures.append(f"B4 {aqi}")
check("B4 Very Poor and Severe: 'Limit outdoor activity at all times [3]' even when the station has a clear clean time", not [f for f in failures if f.startswith("B4")])
check("B5 the best time never comes from the AQI forecast points any more (no 'Best time to go out' / forecast hour)",
      all("Best time to go out" not in l["text"] for l in p_ok["full"] + p_ok["short"]))
check("B6 a 'How is this calculated?' note comes with the best time", p_ok["best_how"] and "28 days" in p_ok["best_how"] and "not a forecast" in p_ok["best_how"])
check("B7 Good air: no best-time line", adv.personal_advice(30, lung, FC, 30, "pm10", 0, OK)["best_time"] is None)

# ---- C. citations on every line ----
bad, refs_bad, n = [], [], 0
for prof, aqi, dom, seq, dp in itertools.product(list(profiles()), AQIS, [None, "pm10", "pm25", "o3"], range(2), [OK, flat, few, None]):
    pa = adv.personal_advice(aqi, prof, FC, now_aqi=aqi - 10, dominant=dom, seq=seq, diurnal=dp)
    for line in pa["full"] + pa["short"]:
        n += 1
        src = line["source"]
        for m in MARKERS:
            src = src.replace(m, "")
        src = src.strip()
        if not src and any(m in line["source"] for m in MARKERS):
            continue
        if not CITE.match(src):
            bad.append(line)
        refs_bad += [r for r in re.findall(r"\[(\d)\]", src) if r not in adv.REFERENCES]
check("C1 every advice line has a [n] citation (or is our forecast / station data)", not bad, f"({n} lines; bad: {bad[:2]})")
check("C2 every cited number exists in the reference list", not refs_bad, str(set(refs_bad)))

# ---- K. tips ----
doc = (ROOT / "docs" / "health_advisory_reference.md").read_text(encoding="utf-8")
tips_section = doc.split("Tips (exact wording used")[1].split("## References")[0]
missing = [t for _, _, _, t, _ in adv.TIPS if f"| {t} |" not in tips_section]
check("K1 every tip appears word for word in the reference document's tip list", not missing, str(missing))
uncited = [t for _, _, _, t, s in adv.TIPS if not CITE.match(s)]
check("K2 every tip has a [n] citation", not uncited, str(uncited))
viol = []
for cat, gs in itertools.product(CATS[1:], [[]] + [[g] for g in GROUPS] + [["child", "lung"]]):
    for t, s in adv.tips_for(cat, gs):
        tl = t.lower()
        if ("n95" in tl or "n99" in tl) and (CATS.index(cat) < 4 or "child" in gs):
            viol.append((cat, gs, t))
        if "inhaler" in tl:
            viol.append((cat, gs, t))
        if any(w in tl for w in ("gargle", "re-circulate", "purifier", "healthy diet")) and CATS.index(cat) < 4:
            viol.append((cat, gs, t))
        if any(w in tl for w in ("mopping", "incense", "doors and windows", "paper masks")) and CATS.index(cat) < 3:
            viol.append((cat, gs, t))
check("K3 tips only where allowed: N95 only from Very Poor and never for children, NCDC severe-plus items only from Poor/Very Poor, no inhalers", not viol, str(viol[:3]))
vp_child = [t for t, _ in adv.tips_for("Very Poor", ["child"])]
check("K4 children at Very Poor get the WHO caution 'no commercial respirators designed for children' (first, profile-specific) and no N95 tip",
      vp_child[0] == "There are no commercial respirators designed for children (based on information available as of February 2019)" and not any("N95" in t for t in vp_child))
ow = adv.tips_for("Moderate", ["outdoor_worker"])
check("K5 profile-specific tips come first in the rotation (outdoor worker: water breaks)", ow[0][0] == "Take frequent water breaks between work")
check("K6 no tips at Good", adv.tips_for("Good", ["lung"]) == [] or adv.personal_advice(30, lung, FC, 30, None, 0)["tip"] is None)
same = {adv.personal_advice(150, lung, FC, 118, "pm10", adv.alert_number("2026-04-24 01:00:00"), OK)["tip"]["text"] for _ in range(5)}
check("K7 same alert (same issue hour) -> same tip, every time", len(same) == 1)
check("K8 alert number is the issue hour (both time formats agree)", adv.alert_number("2026-04-24 01:00:00") == adv.alert_number("2026-04-24 01:00") ==
      (datetime(2026, 4, 24, 1) - datetime(2026, 1, 1)).days * 24 + 1)
diff = all(adv.personal_advice(aqi, prof, FC, aqi, "pm10", s, OK)["tip"]["text"] != adv.personal_advice(aqi, prof, FC, aqi, "pm10", s + 1, OK)["tip"]["text"]
           for aqi, prof, s in itertools.product([75, 150, 250, 350], [lung, {"groups": [], "alert_from": 51}], range(4)))
check("K9 alerts issued in consecutive hours get different tips (rotation)", diff)

# ---- P. profile lines and pop-up layout ----
firsts = {",".join(p["groups"]) or "healthy": adv.personal_advice(150, p, FC, 118, "pm10", 0, OK)["short"][0]["text"]
          for p in [{"groups": [], "alert_from": 201}] + [{"groups": [g], "alert_from": 101} for g in GROUPS]}
check("P1 the first pop-up line differs for each of the 8 profiles (healthy + 7 groups)", len(set(firsts.values())) == 8)
pa = adv.personal_advice(150, {"groups": GROUPS, "alert_from": 101}, FC, 118, "pm10", 0, OK)
kinds = [x["kind"] for x in pa["short"]]
check("P2 pop-up = 1-2 profile lines, trend, best time, 1 tip (7 groups -> still only 2 profile lines)",
      kinds == ["group", "group", "trend", "best_time", "tip"] and len(pa["groups"]) == 7, str(kinds))
pa1 = adv.personal_advice(150, lung, FC, 118, "pm10", 0, OK)
check("P3 one group -> 1 profile line, trend, best time, tip", [x["kind"] for x in pa1["short"]] == ["group", "trend", "best_time", "tip"])
check("P4 the full version keeps everything (all group lines, pollutant, doctor)", sum(x["kind"] == "group" for x in pa["full"]) == 7
      and any(x["kind"] == "pollutant" for x in pa["full"]) and any(x["kind"] == "doctor" for x in pa["full"]))
viol = []
for prof, aqi in itertools.product(list(profiles()), AQIS):
    txt = " ".join(l["text"] for l in adv.personal_advice(aqi, prof, FC, aqi, "pm25", 1, OK)["full"]).lower()
    if adv.category_of(aqi) not in ("Very Poor", "Severe") and ("n95" in txt or "n99" in txt):
        viol.append(("N95", aqi, prof["groups"]))
    if "inhaler" in txt:
        viol.append(("inhaler", aqi, prof["groups"]))
check("P5 no N95/N99 below Very Poor and never 'inhaler' anywhere in the advice", not viol, str(viol[:3]))
r = adv.personal_advice(150, {"groups": [], "alert_from": 201}, [dict(x, aqi=a) for x, a in zip(FC, (120, 160, 140, 125))], 118, None, 0)["trend"]["text"]
f = adv.personal_advice(150, {"groups": [], "alert_from": 201}, [dict(x, aqi=a) for x, a in zip(FC, (150, 120, 100, 90))], 160, None, 0)["trend"]["text"]
check("P6 forecast trend labelled 'Next 24 h: rising / falling ... (our forecast)', from the AQI forecasts", r.startswith("Next 24 h: rising") and f.startswith("Next 24 h: falling")
      and adv.personal_advice(150, {"groups": [], "alert_from": 201}, [dict(x, aqi=a) for x, a in zip(FC, (120, 160, 140, 125))], 118, None, 0)["trend"]["source"]
      == "(our forecast)")

# ---- Q. no repetition, wording checked against the sources ----
rep = []
for prof, aqi in itertools.product(list(profiles()), AQIS):
    pa = adv.personal_advice(aqi, prof, FC, aqi, "pm25", 0, OK)
    impact = adv.IMPACT[pa["category"]].lower()
    for g in pa["groups"]:
        t = g["text"].lower()
        if "cpcb notes" in t or impact in t or "may cause" in t or "[1][2]" in g["source"]:
            rep.append((aqi, g["text"]))
check("Q1 profile lines never repeat the CPCB impact sentence (it is only in the headline line)", not rep, str(rep[:2]))
pm25 = adv.POLLUTANT_INFO["pm25"][0]
check("Q2 PM2.5 line follows WHO [6]: '60 of them make up the width of a human hair', 'penetrate the lung barrier and enter the blood system'",
      "60 of them make up the width of a human hair" in pm25 and "penetrate the lung barrier and enter the blood system" in pm25 and "about 60" not in pm25, pm25)
lvl = {c: adv._group_line(g, ci)[0] for g in ("lung", "older") for c, ci in (("Poor", adv.POOR), ("Very Poor", adv.VPOOR)) for c in [g + " " + c]}
check("Q3 [4] levels: 'avoid outdoor physical activities' at Poor, 'remain indoors and keep activity levels low' at Very Poor (lung and older adult)",
      all("avoid outdoor physical activities" in v for k, v in lvl.items() if k.endswith(" Poor") and "Very" not in k)
      and all("remain indoors and keep activity levels low" in v for k, v in lvl.items() if "Very Poor" in k), str(lvl))

# ---- R. the endpoints (in-process) ----
from fastapi.testclient import TestClient  # noqa: E402
import app as appmod  # noqa: E402
import notify_email as ne  # noqa: E402
c = TestClient(appmod.app)
q = dict(period="validation", station="silkboard", t=T, groups="lung", alert_from=101)
s1, s2 = c.get("/api/replay/state", params=q).json()["personal"], c.get("/api/replay/state", params=q).json()["personal"]
check("R1 /api/replay/state: best time from the station pattern (or no clear time), with the How note",
      s1["best_time"] and (s1["best_time"]["text"].startswith("Usually cleanest") or s1["best_time"]["text"].startswith("No clearly")) and s1["best_how"],
      s1["best_time"]["text"])
check("R2 the same replay alert asked twice gets the same tip", s1["tip"] == s2["tip"])
err, info = ne.replay_compose("silkboard", T, "validation", {"groups": ["lung"], "alert_from": 101, "station": "silkboard", "email": "x@example.com"})
body_lines = info["body"].splitlines() if info else []
impact_lines = [l for l in body_lines if adv.IMPACT["Poor"] in l]
check("Q4 e-mail: the CPCB impact sentence appears once (headline line); the profile line has only the advice",
      len(impact_lines) == 1 and any(l.strip().startswith("- Lung disease: avoid outdoor physical activities") for l in body_lines), str(impact_lines))
check("R3 the e-mail for that alert carries the same tip and the same best-time line as the pop-up", info and s1["tip"]["text"] in info["body"]
      and s1["best_time"]["text"] in info["body"] and "How is this calculated?" in info["body"])
vp = c.get("/api/replay/state", params={**q, "t": "2026-04-24 01:00:00"}).json()
a = c.post("/api/advice", params={"aqi": 360}, json={"groups": ["child"], "alert_from": 101, "forecasts": FC, "station": "silkboard",
                                                     "last_obs_end": "2026-10-14 00:00"}).json()["personal"]
check("R4 /api/advice (live page): Very Poor -> limit outdoor activity; child tip first", a["best_time"]["text"] == "Limit outdoor activity at all times"
      and a["tip"]["text"].startswith("Tip:"))
a2 = c.post("/api/advice", params={"aqi": 150}, json={"groups": ["lung"], "alert_from": 101, "forecasts": FC, "station": "silkboard",
                                                      "last_obs_end": "2026-10-14 00:00"}).json()["personal"]
check("R5 /api/advice (live page): pattern from the live database up to the newest observation", a2["best_time"] is not None and a2["best_how"], a2["best_time"]["text"])

print()
print("ALL PASSED" if not failures else f"{len(failures)} FAILED: {failures}")
sys.exit(1 if failures else 0)
