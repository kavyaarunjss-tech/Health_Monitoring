"""Tests for 'This week's air and your health' (backend/weekly.py, weekly_advice_rules.json, the weekly card).

Synthetic hourly databases make each case exact: clean week, persistent PM2.5 week, mixed week, missing data (16-of-24 rule, 5-of-7 rule),
every profile group, wording (hedged, no "will", every statement cites sources that exist in the reference document), long-term statements
never on non-persistent weeks, the replay clock (only hours <= t; future data cannot change anything), limits equal to the verified values,
trend and 8-hour maximum. The page check runs its own server on port 8040 (DevTools 9340), never port 8000; no e-mail is sent.

usage (project root, aqi env):  python backend\\test_weekly.py
"""
import base64
import itertools
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TMP = Path(tempfile.mkdtemp(prefix="aqi_weekly_"))
os.environ.update(AQI_EMAIL_FAKE="1", AQI_USERS_DB=str(TMP / "users.db"), AQI_SECRET_KEY="weekly-test-" + "v" * 40,
                  AQI_PROFILE_FILE=str(TMP / "profile.json"), AQI_RATE_FILE=str(TMP / "rate.json"))
sys.path.insert(0, str(ROOT / "backend"))
import advice as adv  # noqa: E402
import weekly as W  # noqa: E402

failures = []
FMT = "%Y-%m-%d %H:%M:%S"
T = "2026-03-08 06:00:00"                          # clock; the week is 1-7 March
ALL_GROUPS = ["lung", "heart", "child", "older", "pregnant", "outdoor_worker", "athlete"]


def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  {extra}" if extra else ""))
    if not cond:
        failures.append(name)


def make_db(name, day_values, hours_per_day=24, extra_after_t=None, o3_peak=None):
    """day_values: list of 7 dicts (1-7 March) pollutant -> constant hourly value (missing key = no data that day).
    hours_per_day: int or list of 7 (how many hours of each day have data). extra_after_t: values written after the clock."""
    db = TMP / f"{name}.db"
    rows = []
    start = datetime(2026, 2, 28, 16)                                              # 8 h before day 1 for the 8 h windows
    for k in range(int((datetime.strptime(T, FMT) - start).total_seconds() // 3600) + 1 + 48):
        dt = start + timedelta(hours=k)
        di = (dt.date() - datetime(2026, 3, 1).date()).days
        future = dt > datetime.strptime(T, FMT)
        if future:
            vals = extra_after_t or {}
        elif 0 <= di < 7:
            hp = hours_per_day[di] if isinstance(hours_per_day, list) else hours_per_day
            vals = dict(day_values[di]) if dt.hour < hp else {}
            if o3_peak and dt.hour in range(10, 18) and di == o3_peak[0]:
                vals["o3"] = o3_peak[1]
        else:
            vals = dict(day_values[0])
        rows.append(("st", dt.strftime(FMT), *[vals.get(p) for p in W.POLL]))
    with sqlite3.connect(db) as c:
        c.execute("CREATE TABLE h (station TEXT, datetime TEXT, pm25 REAL, pm10 REAL, no2 REAL, so2 REAL, o3 REAL, co REAL)")
        c.executemany("INSERT INTO h VALUES (?,?,?,?,?,?,?,?)", rows)
    return db


CLEAN = {"pm25": 20, "pm10": 40, "no2": 20, "so2": 10, "o3": 30, "co": 0.5}          # AQI ~ 40 (Good)
PM25_BAD = {"pm25": 75, "pm10": 80, "no2": 30, "so2": 10, "o3": 30, "co": 0.6}       # PM2.5 sub-index 150 (Moderate), dominant PM2.5
POOR = {"pm25": 100, "pm10": 120, "no2": 30, "so2": 10, "o3": 30, "co": 0.6}         # PM2.5 sub-index ~233 (Poor)


def run(db, groups=None, t=T):
    return W.weekly(db, "h", "st", t, groups)


ids = lambda r, k: [i["id"] for i in r["health"][k]]          # noqa: E731

# ---- limits equal the verified values (and the reference document) -------------------------------------------------------------
check("V1 India NAAQS 2009 limits used: PM2.5 60, PM10 100, NO2 80, SO2 80 (24 h), O3 100 (8 h), CO 2 mg/m3 (8 h)",
      W.NAAQS == {"pm25": 60, "pm10": 100, "no2": 80, "so2": 80, "o3": 100, "co": 2})
check("V2 WHO 2021 AQG levels used: PM2.5 15, PM10 45, NO2 25, SO2 40 (24-hour), O3 100 (8-hour), CO 4 mg/m3 (24-hour)",
      W.WHO == {"pm25": 15, "pm10": 45, "no2": 25, "so2": 40, "o3": 100, "co": 4})
doc = (ROOT / "docs" / "health_advisory_reference.md").read_text(encoding="utf-8")
check("V3 the reference document has section 8 with both sources and the limits table", "## 8. Weekly summary" in doc and "\n8. World Health Organization. (2021)" in doc
      and "\n9. Central Pollution Control Board. (2009" in doc and "| PM2.5 | 60 µg/m³, 24 hours | 15 µg/m³, 24-hour |" in doc)

# ---- clean week -------------------------------------------------------------------------------------------------------------------
r = run(make_db("clean", [CLEAN] * 7), ["lung"])
check("C1 clean week: 7 valid days, all Good, level 'clean'", r["valid_days"] == 7 and r["level"] == "clean" and all(d["category"] == "Good" for d in r["days"]),
      str([d["aqi"] for d in r["days"]]))
check("C2 clean week: positive message only; no short-term, long-term statements or actions (no warnings), even for a vulnerable profile",
      ids(r, "clean") == ["C1"] and not r["health"]["short_term"] and not r["health"]["long_term"] and not r["health"]["actions"])
check("C3 clean week: days above the India limit 0; days above WHO counted separately (PM2.5 20 > 15)",
      all(e["days_above_india"] == 0 for e in r["exceedances"]) and {e["pollutant"]: e["days_above_who"] for e in r["exceedances"]}["pm25"] == 7)
rh = run(make_db("clean_h", [CLEAN] * 7), [])
check("C4 clean week, healthy adult: also 'no special precautions' [3]", ids(rh, "clean") == ["C1", "C2"])

# ---- persistent PM2.5 week ----------------------------------------------------------------------------------------------------------
dbp = make_db("persist", [PM25_BAD] * 7)
r = run(dbp, [])
check("P1 persistent PM2.5 week: AQI 150 every day, Moderate, level 'persistent', main pollutant PM2.5",
      r["level"] == "persistent" and all(d["aqi"] == 150 for d in r["days"]) and r["dominant"] == "pm25" and r["worst_category"] == "Moderate")
ex = {e["pollutant"]: e for e in r["exceedances"]}
check("P2 PM2.5 75 > India 60 and > WHO 15 on all 7 days; PM10 80 below India 100 but above WHO 45",
      ex["pm25"]["days_above_india"] == 7 and ex["pm25"]["days_above_who"] == 7 and ex["pm10"]["days_above_india"] == 0 and ex["pm10"]["days_above_who"] == 7)
check("P3 persistent week: short-term (incl. the PM2.5 statement), long-term awareness and actions are shown",
      "S10" in ids(r, "short_term") and ids(r, "long_term") == ["L1"] and r["health"]["actions"])

# ---- mixed week -----------------------------------------------------------------------------------------------------------------------
r = run(make_db("mixed", [CLEAN, PM25_BAD, CLEAN, POOR, CLEAN, PM25_BAD, CLEAN]), ["lung"])
check("M1 mixed week (3 polluted days of 7): level 'episode', worst Poor, NOT persistent", r["level"] == "episode" and r["days_moderate_or_worse"] == 3
      and r["worst_category"] == "Poor" and not r["persistent"])
check("M2 mixed week: short-term statements and actions, but NO long-term statements", r["health"]["short_term"] and not r["health"]["long_term"]
      and "S8" in ids(r, "short_term") and "A3" in ids(r, "actions"))

# ---- missing data ---------------------------------------------------------------------------------------------------------------------
r = run(make_db("missing", [PM25_BAD] * 7, hours_per_day=[24, 24, 24, 24, 10, 10, 10]), ["lung"])
check("D1 3 days with only 10 hours: 4 valid days -> 'not enough data', no health statements at all", r["valid_days"] == 4 and not r["enough"]
      and not any(r["health"].values()))
r16 = run(make_db("h16", [PM25_BAD] * 7, hours_per_day=[16] * 7))
r15 = run(make_db("h15", [PM25_BAD] * 7, hours_per_day=[16, 16, 16, 16, 16, 15, 15]))
check("D2 CPCB 16-of-24 rule: 16 hours -> valid day; 15 hours -> not valid", r16["valid_days"] == 7 and r15["valid_days"] == 5 and r15["enough"])
check("D3 exactly 5 valid days is enough; the days without data show as 'no data'", r15["days"][5]["aqi"] is None and r15["days"][5]["valid"] is False)

# ---- groups -----------------------------------------------------------------------------------------------------------------------
dbv = make_db("vpoor", [PM25_BAD, PM25_BAD, POOR, POOR, {"pm25": 150, "pm10": 300, "no2": 30, "so2": 10, "o3": 30, "co": 0.6}, PM25_BAD, PM25_BAD])
expect = {"lung": (["S2"], ["L2"], ["A7", "A2", "A3", "A5"]), "heart": (["S3"], ["L3"], ["A7", "A2"]), "child": (["S4"], [], ["A12", "A2"]),
          "older": (["S5"], [], ["A2"]), "pregnant": (["S6"], ["L4"], ["A2"]), "outdoor_worker": (["S7"], [], ["A10", "A2"]),
          "athlete": (["S7"], [], ["A2"]), "healthy": ([], [], ["A1", "A4"])}
own = {"lung": {"S2", "L2", "A7"}, "heart": {"S3", "L3", "A7"}, "child": {"S4", "A12"}, "older": {"S5"}, "pregnant": {"S6", "L4"},
       "outdoor_worker": {"S7", "A10"}, "athlete": {"S7"}, "healthy": {"A1", "A4"}}
bad = []
for g, (s_, l_, a_) in expect.items():
    r = run(dbv, [] if g == "healthy" else [g])
    got = set(ids(r, "short_term")) | set(ids(r, "long_term")) | set(ids(r, "actions"))
    if not (set(s_) <= set(ids(r, "short_term")) and set(l_) <= set(ids(r, "long_term")) and set(a_) <= set(ids(r, "actions"))):
        bad.append((g, "missing", sorted(set(s_ + l_ + a_) - got)))
    others = set().union(*[v for k, v in own.items() if k != g]) - own[g]          # items that belong only to OTHER groups
    leak = got & others
    if leak:
        bad.append((g, "other groups' items", sorted(leak)))
check("G1 each profile (lung, heart, child, older, pregnancy, outdoor worker, exerciser, healthy) gets its own statements and actions, and not other groups'",
      not bad, str(bad))
r = run(dbv, ["child"])
check("G2 child on a Very Poor week: WHO 'no respirators designed for children', and no N95 advice", "A12" in ids(r, "actions") and "A11" not in ids(r, "actions"))
r = run(dbv, ["lung"])
check("G3 adults on a Very Poor week get the N95/N99 action with the WHO caution", "A11" in ids(r, "actions"))
r = run(make_db("o3dom", [{"pm25": 20, "pm10": 40, "no2": 20, "so2": 10, "o3": 150, "co": 0.5}] * 7), ["lung"])
check("G4 ozone week, lung disease: the ozone-and-asthma statement appears", r["dominant"] == "o3" and "S12" in ids(r, "short_term"))

# ---- wording ----------------------------------------------------------------------------------------------------------------------------
rules = W.RULES
items = [x for k in ("clean", "short_term", "long_term", "actions") for x in rules[k]]
refs_in_doc = set(re.findall(r"^(\d+)\. ", doc.split("## References")[1], re.M))
bad_words, bad_src, unhedged = [], [], []
for x in items:
    t = x["text"].lower()
    if re.search(r"\bwill\b|\bdiagnos|\byou have (asthma|copd|heart|a disease)|\bcauses\b", t):
        bad_words.append(x["id"])
    if not x["sources"] or any(s not in adv.REFERENCES or s not in refs_in_doc for s in x["sources"]):
        bad_src.append(x["id"])
for x in rules["short_term"] + rules["long_term"]:
    if not re.search(r"\bmay\b|linked|higher risk|vulnerable|main pollutant", x["text"].lower()):
        unhedged.append(x["id"])
check("W1 no 'will', 'causes', diagnosis wording in any statement or action", not bad_words, str(bad_words))
check("W2 every statement and action cites sources that exist in the site's reference list AND in the reference document", not bad_src, str(bad_src))
check("W3 every health statement is hedged ('may', 'is linked to', 'higher risk', 'vulnerable')", not unhedged, str(unhedged))
check("W4 long-term statements speak of sustained / long-term exposure, never of this week", all(re.search(r"sustained|long-term", x["text"].lower())
      for x in rules["long_term"]) and not any("this week" in x["text"].lower() for x in rules["long_term"]))
check("W5 the weekly response always carries the disclaimer", run(dbp)["disclaimer"] == "General information from public health guidance, not medical advice.")
check("W6 every rule's text is documented word for word in the reference document (section 8)", all(x["text"] in doc for x in items))

# ---- long-term never on non-persistent weeks ------------------------------------------------------------------------------------------
leaks = []
for n_bad in range(0, 4):
    for combo in itertools.combinations(range(7), n_bad):
        if n_bad > 1 and combo[0] != 0:
            continue                                                                   # a sample of placements is enough
        dv = [POOR if i in combo else CLEAN for i in range(7)]
        db = make_db(f"np_{n_bad}_{'_'.join(map(str, combo))}", dv)
        for g in [[]] + [[x] for x in ALL_GROUPS]:
            r = run(db, g)
            if r["health"]["long_term"] or r["persistent"]:
                leaks.append((n_bad, combo, g))
check("L1 weeks with 0-3 polluted days: never 'persistent', never a long-term statement, for every profile", not leaks, str(leaks[:3]))
r = run(make_db("four", [POOR, POOR, POOR, POOR, CLEAN, CLEAN, CLEAN]), [])
check("L2 exactly 4 polluted days -> persistent, long-term awareness shown", r["persistent"] and ids(r, "long_term") == ["L1"])

# ---- review changes 26 Oct: S1 thresholds, C3, A10 source ------------------------------------------------------------------------------
VULN = [["lung"], ["heart"], ["child"], ["older"], ["pregnant"], ["outdoor_worker"], ["athlete"]]
mod_db = make_db("rv_mod", [PM25_BAD] * 7)                                        # worst day Moderate
poor_db = make_db("rv_poor", [CLEAN, PM25_BAD, CLEAN, POOR, CLEAN, CLEAN, CLEAN])  # worst day Poor
s1_mod = {tuple(g): "S1" in ids(run(mod_db, g), "short_term") for g in VULN + [[]]}
s1_poor_h = "S1" in ids(run(poor_db, []), "short_term")
check("N1 S1 (headache, giddiness, ...): every vulnerable group from a Moderate worst day; healthy adults NOT on a Moderate week, only from Poor",
      all(s1_mod[tuple(g)] for g in VULN) and not s1_mod[()] and s1_poor_h, str(s1_mod))
SAT = {"pm25": 45, "pm10": 60, "no2": 20, "so2": 10, "o3": 30, "co": 0.5}          # PM2.5 sub-index 75 (Satisfactory)
sat_db = make_db("rv_sat", [CLEAN, SAT, CLEAN, CLEAN, SAT, CLEAN, CLEAN])
c3 = {tuple(g): ids(run(sat_db, g), "clean") for g in VULN + [[]]}
good_c3 = ids(run(make_db("rv_good", [CLEAN] * 7), ["lung"]), "clean")
c3_rule = next(x for x in rules["clean"] if x["id"] == "C3")
check("N2 C3 on a clean week that reached Satisfactory: every vulnerable group gets C1 + C3, healthy adults C1 + C2 (no C3); an all-Good week has no C3",
      all(c3[tuple(g)] == ["C1", "C3"] for g in VULN) and c3[()] == ["C1", "C2"] and good_c3 == ["C1"], str(c3))
check("N3 C3 uses the source wording 'may cause minor breathing discomfort to sensitive people' [1][2][3]; CPCB report Table 3.12 (p. 36) quoted",
      c3_rule["text"] == "At Satisfactory levels, air may cause minor breathing discomfort to sensitive people." and c3_rule["sources"] == ["1", "2", "3"]
      and "Table 3.12" in c3_rule["basis"] and 'Statements for AQI Categories", printed p. 36' in doc
      and "Satisfactory (51–100) May cause minor breathing discomfort to sensitive people." in doc
      and "May cause: Minor breathing discomfort in vulnerable populations" in doc)
a10 = next(x for x in rules["actions"] if x["id"] == "A10")
check("N4 A10 (water breaks) traced to the ASHA handbook [3] p. 31 AIR-POLLUTION table, exact quote 'Ensure taking frequent water breaks between work'",
      a10["sources"] == ["3"] and "p. 31" in a10["basis"] and "'Ensure taking frequent water breaks between work'" in a10["basis"]
      and "Ensure taking frequent water breaks between work" in doc and "AQI Levels, Health Effects and Protective Health Measures" in doc)

# ---- pregnancy outcomes (low birth weight / intrauterine growth restriction) only in "If this continues" --------------------------------
OUTCOME = re.compile(r"birth|intrauterine|growth|f(o)?etal|f(o)?etus|gestation|unborn|bab(y|ies)|womb|miscarr|preterm|premature", re.I)
outside = [x["id"] for k in ("clean", "short_term", "actions") for x in rules[k] if OUTCOME.search(x["text"])]
inside = [x["id"] for x in rules["long_term"] if OUTCOME.search(x["text"])]
l4 = next(x for x in rules["long_term"] if x["id"] == "L4")
check("PG1 rule table: pregnancy-outcome wording (birth weight, growth restriction, ...) only in the long-term section (L4, pregnant only, persistent weeks)",
      not outside and inside == ["L4"] and l4["groups"] == ["pregnant"] and l4["levels"] == ["persistent"], f"outside={outside} inside={inside}")
weeks = {"clean": [CLEAN] * 7, "mixed": [CLEAN, PM25_BAD, CLEAN, POOR, CLEAN, PM25_BAD, CLEAN], "three": [POOR] * 3 + [CLEAN] * 4,
         "four": [POOR] * 4 + [CLEAN] * 3, "persist": [PM25_BAD] * 7, "poor": [POOR] * 7,
         "vpoor": [PM25_BAD, PM25_BAD, POOR, POOR, {"pm25": 150, "pm10": 300, "no2": 30, "so2": 10, "o3": 30, "co": 0.6}, PM25_BAD, PM25_BAD]}
viol, seen_l4 = [], []
for wk, dv in weeks.items():
    db = make_db("pg_" + wk, dv)
    for g in (["pregnant"], ["pregnant", "lung"], ["pregnant", "child"], ["pregnant", "outdoor_worker"], ALL_GROUPS):
        r = run(db, g)
        for sec in ("clean", "short_term", "actions"):
            viol += [(wk, g, sec, i["id"]) for i in r["health"][sec] if OUTCOME.search(i["text"])]
        has_l4 = "L4" in ids(r, "long_term")
        if has_l4 != bool(r["persistent"]):
            viol.append((wk, g, "L4 shown" if has_l4 else "L4 missing", r["persistent"]))
        seen_l4.append(has_l4)
check("PG2 every week type x pregnancy profiles: no pregnancy-outcome text in 'This week' / 'This week may affect you' / actions; L4 exactly on persistent weeks",
      not viol and any(seen_l4) and not all(seen_l4), str(viol[:4]))
r = run(make_db("pg_mixed2", weeks["mixed"]), ["pregnant"])
check("PG3 pregnancy on a NON-persistent polluted week: only the vulnerability statement S6 in short-term, no long-term section",
      "S6" in ids(r, "short_term") and not r["health"]["long_term"] and not OUTCOME.search(next(i["text"] for i in r["health"]["short_term"] if i["id"] == "S6")))
ui_src = (ROOT / "frontend" / "ui.js").read_text(encoding="utf-8")
wk_src = ui_src[ui_src.index("function renderWeekly"):ui_src.index("async function loadWeekly")]
check("PG4 the card code adds no health wording of its own (no pregnancy-outcome words in renderWeekly)", not OUTCOME.search(wk_src))
import export_weekly_review as EXP  # noqa: E402
review = (ROOT / "docs" / "weekly_advice_review.md").read_text(encoding="utf-8")
check("X1 docs/weekly_advice_review.md is up to date with the rule table and lists all 33 statements (C1-C3, S1-S12, L1-L4, A1-A14) word for word",
      review == EXP.build() and all(f"| {x['id']} | {x['text']} |" in review for x in items) and len(items) == 33)

# ---- hedged cause wording ---------------------------------------------------------------------------------------------------------------
CAUSE = re.compile(r"\bcaus(e|es|ed|ing)\b", re.I)


def unhedged_causes(text):
    """every 'cause/causes/causing' must be hedged by 'may' / 'can' just before it, or be attributed ('WHO calls ...'); 'caused by a chemical
    reaction' describes how ozone forms (not a health effect)."""
    out = []
    for m in CAUSE.finditer(text):
        before = text[max(0, m.start() - 30):m.start()].lower()
        if re.search(r"\b(may|can)\s+$", before) or "who calls" in text[max(0, m.start() - 60):m.start()].lower() \
                or text[m.start():m.start() + 30].lower().startswith("caused by a chemical"):
            continue
        out.append(text[max(0, m.start() - 40):m.end() + 20])
    return out


texts = [(x["id"], x["text"]) for x in items] + [(x["id"], W.past_tense(x["text"])) for x in items] + \
        [("advice:" + k, v[0]) for k, v in adv.POLLUTANT_INFO.items()] + [("tip", t[3]) for t in adv.TIPS]
bad_cause = [(i, u) for i, t in texts for u in unhedged_causes(t)]
check("H1 no unhedged 'causes' / 'causing' in any weekly rule (present and past tense), pollutant line or tip ('may/can cause', or attributed to WHO)",
      not bad_cause, str(bad_cause[:3]))
s11 = next(x["text"] for x in items if x["id"] == "S11")
check("H2 PM10: '... lodge deep inside the lungs, which can cause irritation and inflammation' [6] (weekly S11 and the advice pollutant line)",
      s11.endswith("lodge deep inside the lungs, which can cause irritation and inflammation.") and "which can cause irritation and inflammation" in adv.POLLUTANT_INFO["pm10"][0]
      and unhedged_causes("particles that lodge deep inside the lungs, causing irritation") != [], s11)

# ---- stale live data: the LAST AVAILABLE week, never "this week"; replay keeps "this week" -----------------------------------------
with sqlite3.connect(ROOT / "data" / "aqi.db") as c:
    newest = c.execute("SELECT MAX(datetime) FROM hourly WHERE station='silkboard' AND (pm25 IS NOT NULL OR pm10 IS NOT NULL)").fetchone()[0]
END = datetime.strptime(newest, FMT) + timedelta(hours=1)
THIS = re.compile(r"\bthis week", re.I)
alltext = lambda r: " ".join(i["text"] for v in r["health"].values() for i in v)          # noqa: E731
st = W.live_weekly("silkboard", ALL_GROUPS, now=END + timedelta(hours=30))
fr = W.live_weekly("silkboard", ALL_GROUPS, now=END + timedelta(hours=5))
check("ST1 live, newest data 30 h old: marked stale (age 30 h), and no health text says 'this week' (past tense 'that week')",
      st["data"]["stale"] and st["data"]["age_hours"] == 30.0 and st["data"]["mode"] == "live" and not THIS.search(alltext(st)), json.dumps(st["data"]))
check("ST2 live, newest data 5 h old: NOT stale, texts unchanged (same as the rule table)",
      not fr["data"]["stale"] and fr["data"]["age_hours"] == 5.0 and all(i["text"] in [x["text"] for x in items] for v in fr["health"].values() for i in v))
b24 = W.live_weekly("silkboard", [], now=END + timedelta(hours=24))["data"]["stale"]
b25 = W.live_weekly("silkboard", [], now=END + timedelta(hours=24, minutes=6))["data"]["stale"]
check("ST3 boundary: exactly 24 h old -> current week; 24.1 h -> stale", b24 is False and b25 is True)
rp = W.replay_weekly("silkboard", "2026-04-24 02:00:00", ["lung"])
check("ST4 replay is never stale (relative to the replay clock) and keeps 'This week's main pollutant ...'",
      rp["data"] == {"mode": "replay", "stale": False} and THIS.search(alltext(rp)))
left = [x["id"] for x in items if THIS.search(W.past_tense(x["text"]))]
check("ST5 the past-tense conversion covers every rule text (no 'this week' left in any of the 32)", not left, str(left))
os.environ["AQI_LIVE_NOW"] = (END + timedelta(hours=40)).strftime("%Y-%m-%d %H:%M")
from fastapi.testclient import TestClient as _TC  # noqa: E402
import app as _app  # noqa: E402
lv = _TC(_app.app).get("/api/weekly", params={"station": "silkboard", "mode": "live"}).json()
check("ST6 /api/weekly live uses the live clock (test override AQI_LIVE_NOW): 40 h old -> stale", lv["data"]["stale"] and lv["data"]["age_hours"] == 40.0,
      json.dumps(lv["data"]))

# ---- trend and 8-hour maximum ---------------------------------------------------------------------------------------------------------
rise = run(make_db("rise", [CLEAN] * 4 + [PM25_BAD] * 3))
fall = run(make_db("fall", [PM25_BAD] * 4 + [CLEAN] * 3))
steady = run(make_db("steady", [PM25_BAD] * 7))
check("R1 trend: last 3 days vs previous 4 -> rising / falling / steady", rise["trend"]["direction"] == "rising" and fall["trend"]["direction"] == "falling"
      and steady["trend"]["direction"] == "steady", f"{rise['trend']} {fall['trend']} {steady['trend']}")
small = run(make_db("small", [PM25_BAD] * 4 + [{**PM25_BAD, "pm25": 78}] * 3))
check("R2 a small change (150 -> 160 AQI, within max(10 points, 10 %)) counts as steady", small["trend"]["direction"] == "steady", str(small["trend"]))
r = run(make_db("o3peak", [CLEAN] * 7, o3_peak=(2, 120)))
o3 = {e["pollutant"]: e for e in r["exceedances"]}["o3"]
check("R3 O3 uses the daily maximum 8-hour mean: an 8-hour peak of 120 on one day counts above India 100 and WHO 100 once",
      r["days"][2]["values"]["o3"] == 120 and o3["days_above_india"] == 1 and o3["days_above_who"] == 1, str(r["days"][2]["values"]))

# ---- replay clock -------------------------------------------------------------------------------------------------------------------
check("K1 the week is the 7 complete days before the clock (06:00 on 8 Mar -> 1-7 Mar; 23:00 on 7 Mar -> 1-7 Mar; 22:00 on 7 Mar -> 28 Feb-6 Mar)",
      [str(x) for x in W.week_window("2026-03-08 06:00:00")] == ["2026-03-01", "2026-03-07"]
      and [str(x) for x in W.week_window("2026-03-07 23:00:00")] == ["2026-03-01", "2026-03-07"]
      and [str(x) for x in W.week_window("2026-03-07 22:00:00")] == ["2026-02-28", "2026-03-06"])
a = run(make_db("nofuture", [PM25_BAD] * 7))
b = run(make_db("future", [PM25_BAD] * 7, extra_after_t={"pm25": 900, "pm10": 900, "no2": 900, "so2": 900, "o3": 900, "co": 50}))
check("K2 extreme data after the clock changes nothing (only hours <= t are read)", json.dumps(a["days"]) == json.dumps(b["days"]))
shutil.copy(ROOT / "data" / "replay.db", TMP / "replay_copy.db")
TR = "2026-04-24 02:00:00"
with sqlite3.connect(TMP / "replay_copy.db") as c:
    c.execute("UPDATE replay_obs SET pm25=999, pm10=999, no2=999, so2=999, o3=999, co=99 WHERE station='silkboard' AND datetime > ?", (TR,))
real = W.replay_weekly("silkboard", TR, ["lung"])
pois = W.weekly(TMP / "replay_copy.db", "replay_obs", "silkboard", TR, ["lung"])
check("K3 real replay data (Silk Board, 24 Apr 02:00): identical result when every later hour is replaced by 999 (no leakage)",
      json.dumps(real["days"]) == json.dumps(pois["days"]) and real["window"]["last"] == "2026-04-23", f"{real['window']} {[d['aqi'] for d in real['days']]}")
r1 = W.replay_weekly("silkboard", "2026-04-24 22:00:00", [])
r2 = W.replay_weekly("silkboard", "2026-04-24 23:00:00", [])
check("K4 moving the replay clock past 23:00 adds the completed day to the week", r1["window"]["last"] == "2026-04-23" and r2["window"]["last"] == "2026-04-24")

# ---- API (in-process) -----------------------------------------------------------------------------------------------------------------
from fastapi.testclient import TestClient  # noqa: E402
import app as appmod  # noqa: E402
c = TestClient(appmod.app)
a1 = c.get("/api/weekly", params={"station": "silkboard", "mode": "replay", "t": TR, "groups": "lung"})
a2 = c.get("/api/weekly", params={"station": "silkboard", "mode": "live"})
a3 = c.get("/api/weekly", params={"station": "silkboard", "mode": "replay", "t": "yesterday"})
a4 = c.get("/api/weekly", params={"station": "delhi", "mode": "live"})
check("A1 /api/weekly: replay 200 (7 days, health per profile), live 200, bad clock 400, unknown station 404",
      a1.status_code == 200 and len(a1.json()["days"]) == 7 and a1.json()["health"]["short_term"] and a2.status_code == 200
      and a3.status_code == 400 and a4.status_code == 404, f"{a1.status_code} {a2.status_code} {a3.status_code} {a4.status_code}")

# ---- page (headless Chrome, own server on port 8040) --------------------------------------------------------------------------------
import subprocess  # noqa: E402
import urllib.request  # noqa: E402
import test_pages_logged_in as P  # noqa: E402
P.PORT, P.DEVTOOLS = 8040, 9340
P.BASE = f"http://127.0.0.1:{P.PORT}"
P.TMP = TMP / "ui"; P.TMP.mkdir()
OUT = ROOT / "screenshots_preview" / "weekly"; OUT.mkdir(parents=True, exist_ok=True)
proc = P.start_server()
chrome = subprocess.Popen([P.CHROME, "--headless=new", "--disable-gpu", "--no-sandbox", f"--remote-debugging-port={P.DEVTOOLS}",
                           f"--user-data-dir={P.TMP / 'chrome'}", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(60):
        try:
            page = next(t for t in json.loads(urllib.request.urlopen(f"http://127.0.0.1:{P.DEVTOOLS}/json", timeout=2).read()) if t["type"] == "page")
            break
        except Exception:
            time.sleep(0.5)
    tab = P.Tab(page["webSocketDebuggerUrl"])
    sess = P.api_session(first=True)                                                   # profile: lung + heart, age 63 (older adult)

    def card_at(hour, station="silkboard", width=1366, height=900, mobile=False, shot=None, period="validation"):
        tab.cmd("Emulation.setDeviceMetricsOverride", width=width, height=height, deviceScaleFactor=2 if mobile else 1, mobile=mobile)
        tab.set_session(sess)
        tab.goto(P.BASE + f"/?pauseonalert=0&station={station}&period={period}")
        tab.wait("S.hours.length > 0", 25)
        tab.wait("!!document.getElementById('weeklyCard').dataset.clock", 25)       # the start-up jump has been displayed
        tab.pump(1.0)
        for _ in range(4):        # the page's own start-up jump (to the next event) can land after ours: set the hour until it stays
            clock = tab.js("(async () => { stop(); clearAlert('x'); S.idx = S.hours.findIndex(h => h >= %s); await show(); return S.hours[S.idx]; })()" % json.dumps(hour))
            tab.wait("document.getElementById('weeklyCard').dataset.clock === %s" % json.dumps(clock), 15)
            tab.pump(0.8)
            if tab.js("document.getElementById('weeklyCard').dataset.clock") == clock:
                break
        tab.js("clearAlert('x'); document.getElementById('weeklyCard').scrollIntoView({block: 'start'}); window.scrollBy(0, -130)")
        tab.pump(0.3)
        if shot:
            (OUT / shot).write_bytes(base64.b64decode(tab.cmd("Page.captureScreenshot", format="png")["data"]))
        return card_info()

    def card_info():
        return tab.js("""(() => { const c = document.getElementById('weeklyCard'); return { text: c.textContent, bars: c.querySelectorAll('.wk-day').length,
            title: c.querySelector('h2') ? c.querySelector('h2').textContent : '', stale: c.querySelector('.wk-stale') ? c.querySelector('.wk-stale').textContent : '',
            notes: c.querySelector('.wk-notes') ? c.querySelector('.wk-notes').textContent : '', chip: c.querySelector('.wk-chip') ? c.querySelector('.wk-chip').textContent : '',
            sections: Array.from(c.querySelectorAll('h3')).map(h => h.textContent), refs: c.querySelectorAll('.wk-sources li').length,
            cites: c.querySelectorAll('.wk-list .src a').length, items: c.querySelectorAll('.wk-list li').length }; })()""")

    u = card_at(TR, shot="weekly_persistent_desktop.png")
    check("U1 replay page (Silk Board, 24 Apr): weekly card with 7 bars, trend, main pollutant, India/WHO table and the four sections of a persistent week",
          u["bars"] == 7 and "17 Apr – 23 Apr" in u["text"] and u["chip"].startswith("↗ Last 7 days: rising") and "Main pollutant" in u["text"] and "Days above India limit" in u["text"]
          and u["sections"] == ["This week may affect you", "If this continues", "What you can do"], json.dumps(u)[:300])
    check("U2 every statement on the card shows its source numbers, the sources list has links, the disclaimer is shown",
          u["cites"] >= u["items"] and u["refs"] >= 3 and "General information from public health guidance, not medical advice." in u["text"])
    check("U3 no JavaScript errors", not tab.errors, str(tab.errors))
    note = tab.js("(document.querySelector('#weeklyCard .wk-chipnote') || {}).textContent || ''")
    check("U9 note under the chips: 'Main pollutant = the pollutant with the highest CPCB sub-index on most days; the WHO column compares against stricter "
          "guideline levels.'", note == "Main pollutant = the pollutant with the highest CPCB sub-index on most days; the WHO column compares against stricter "
          "guideline levels.", note)
    check("U6 replay keeps 'This week' (relative to the replay clock): title, headings, trend chip 'Last 7 days', no 'Data feed stopped' line",
          u["title"] == "This week's air and your health" and "This week may affect you" in u["sections"] and not u["stale"], json.dumps(u)[:200])
    n9, n8 = u["notes"].count("[9]"), u["notes"].count("[8]")
    check("U7 footnote under the pollutant table: each source number once ('... consecutive days [9]. ... is met [8].'), no '[9]. [9]'",
          n9 == 1 and n8 == 1 and "]. [" not in u["notes"] and u["notes"].rstrip().endswith("[8]."), u["notes"])
    card_at(TR, width=390, height=844, mobile=True, shot="weekly_persistent_mobile.png")
    v = card_at("2026-07-10 12:00:00", station="mysuru", shot="weekly_clean_desktop.png", period="test")
    check("U4 clean week on the page (Mysuru, July): the positive message, no warnings, no 'If this continues'",
          "no day this week reached Moderate or worse" in v["text"] and "If this continues" not in v["sections"] and "What you can do" not in v["sections"], str(v["sections"]))
    tab.cmd("Emulation.setDeviceMetricsOverride", width=1366, height=900, deviceScaleFactor=1, mobile=False)
    tab.goto(P.BASE + "/profile.html")
    tab.wait("document.getElementById('weeklyCard').dataset.clock", 20)
    tab.pump(0.5)
    pf = card_info()
    check("U5 the profile page shows the weekly card for the home station (live data, 40 h old here: 'Last available week')",
          "home station" in pf["text"] and pf["title"].startswith("Last available week (") and pf["stale"].startswith("Data feed stopped") and not tab.errors)
    tab.goto(P.BASE + "/live.html")
    tab.wait("document.getElementById('weeklyCard').dataset.clock", 25)
    tab.pump(0.8)
    tab.js("document.getElementById('weeklyCard').scrollIntoView({block: 'start'}); window.scrollBy(0, -130)")
    tab.pump(0.3)
    (OUT / "weekly_live_stale_desktop.png").write_bytes(base64.b64decode(tab.cmd("Page.captureScreenshot", format="png")["data"]))
    lvp = card_info()
    shown = tab.js("document.getElementById('station').value")
    exp_age = json.loads(urllib.request.urlopen(P.BASE + f"/api/weekly?station={shown}&mode=live", timeout=30).read())["data"]["age_hours"]
    allowed = {"That week", "During that week, air like this may affect you", "If air like that week's continues", "What you can do"}
    rng = re.match(r"Last available week \((\d+)–(\d+) (\w+)\)$|Last available week \((\d+ \w+) – (\d+ \w+)\)$", lvp["title"])
    check("U8 live page, newest data >= 40 h old (test clock): title 'Last available week (7–13 Oct)', line 'Data feed stopped: newest data is 40 h old; this is not the current "
          "week.', past-tense headings, chip 'That week: ...', and 'this week' nowhere on the card",
          rng is not None and lvp["stale"] == f"Data feed stopped: newest data is {round(exp_age)} h old; this is not the current week." and exp_age >= 40
          and set(lvp["sections"]) <= allowed
          and lvp["sections"] and lvp["chip"].split(": ")[0].endswith("That week") and not re.search(r"this week", lvp["text"], re.I) and not tab.errors,
          json.dumps({k: lvp[k] for k in ("title", "stale", "sections", "chip")}))
    tab.ws.close()
finally:
    chrome.kill(); proc.kill()

print()
print("ALL PASSED" if not failures else f"{len(failures)} FAILED: {failures}")
sys.exit(1 if failures else 0)
