"""'This week's air and your health': a 7-day pollutant summary for one station and evidence-based, hedged health awareness per profile.

Tracking (replay: relative to the replay clock; live: up to the newest observation), only hours <= that time are read:
  * the 7 COMPLETE calendar days before it (a day is complete when its 23:00 hour is not after the clock);
  * daily 24 h means of PM2.5, PM10, NO2, SO2 (CPCB: valid with >= 16 of 24 hours); daily maximum 8 h mean of O3 and CO (8 h windows valid with
    >= 6 of 8 hours, the day with >= 16 valid hours); CO also as a 24 h mean for the WHO 24-hour guideline;
  * daily AQI with the CPCB formula (aq_clean.aqi_from_averages: max sub-index, >= 3 pollutants incl. PM2.5 or PM10), category, main pollutant;
  * days above the Indian NAAQS limit and above the WHO 2021 guideline, per pollutant; trend; main pollutant of the week; persistence.
Health text comes ONLY from weekly_advice_rules.json; each item carries source numbers that exist in docs/health_advisory_reference.md.
"""
import json
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model"))
sys.path.insert(0, str(ROOT / "backend"))
import aq_clean  # noqa: E402
import advice as adv  # noqa: E402

FMT = "%Y-%m-%d %H:%M:%S"
POLL = ["pm25", "pm10", "no2", "so2", "o3", "co"]

# ---- limits, verified 25 Oct 2026 (exact quotes in docs/health_advisory_reference.md section 8) --------------------------------------
# India: National Ambient Air Quality Standards, CPCB notification of 18 Nov 2009 (Gazette of India), "Industrial, Residential, Rural and
# Other Area" column [9]. 24 h for PM/NO2/SO2; 8 h for O3 and CO (CO in mg/m3).
NAAQS = {"pm25": 60, "pm10": 100, "no2": 80, "so2": 80, "o3": 100, "co": 2}
NAAQS_AVG = {"pm25": "24 h", "pm10": "24 h", "no2": "24 h", "so2": "24 h", "o3": "8 h", "co": "8 h"}
# WHO global air quality guidelines 2021, Table 0.1 "AQG level" (short-term averaging times) [8]. CO in mg/m3 (24-hour).
WHO = {"pm25": 15, "pm10": 45, "no2": 25, "so2": 40, "o3": 100, "co": 4}
WHO_AVG = {"pm25": "24 h", "pm10": "24 h", "no2": "24 h", "so2": "24 h", "o3": "8 h", "co": "24 h"}
UNITS = {"pm25": "µg/m³", "pm10": "µg/m³", "no2": "µg/m³", "so2": "µg/m³", "o3": "µg/m³", "co": "mg/m³"}

# ---- rules (design decisions of this project; thresholds as named constants) -------------------------------------------------------------
DAYS = 7                    # length of the summary
MIN_DAY_HOURS = 16          # CPCB: a 24 h average needs >= 16 of 24 valid hours
MIN_8H_HOURS = 6            # CPCB: an 8 h average needs >= 6 of 8 valid hours
MIN_VALID_DAYS = 5          # fewer than 5 of 7 days with a valid AQI -> "Not enough data for a weekly summary", no health statements
PERSIST_DAYS = 4            # persistent pollution: >= 4 of the last 7 valid days ...
PERSIST_AQI = 101           # ... with AQI >= 101 (Moderate or worse)
TREND_ABS, TREND_REL = 10, 0.10     # trend (mean of the last 3 days vs the previous 4): steady unless the change exceeds max(10 AQI points, 10 %)
RULES = json.loads((ROOT / "backend" / "weekly_advice_rules.json").read_text(encoding="utf-8"))
for _k in ("clean", "short_term", "long_term", "actions"):          # **...** in the JSON = bold on the page (presentation only): "marked" keeps the
    for _r in RULES[_k]:                                             # markers, "text" is the plain wording every test and document compares against
        _r["marked"], _r["text"] = _r["text"], _r["text"].replace("**", "")
CAT_RANK = {c: i for i, c in enumerate(adv.ORDER)}


# ---- data ------------------------------------------------------------------------------------------------------------------------------
def load_hours(db, table, station, start, end):
    """Hourly rows for station with start <= datetime <= end (hour-start labels), indexed by datetime, all 6 pollutants."""
    with sqlite3.connect(db, timeout=30) as c:
        df = pd.read_sql_query(f"SELECT datetime, {', '.join(POLL)} FROM {table} WHERE station=? AND datetime>=? AND datetime<=? ORDER BY datetime",
                               c, params=(station, start, end))
    df["datetime"] = pd.to_datetime(df["datetime"])
    return df.set_index("datetime")


def week_window(t):
    """The 7 complete calendar days before the clock t (label 'YYYY-MM-DD HH:MM:SS'): (first day, last day)."""
    t0 = datetime.strptime(t, FMT)
    last = t0.date() if t0.hour == 23 else t0.date() - timedelta(days=1)
    return last - timedelta(days=DAYS - 1), last


def summarize(hours, t):
    """Daily values for the 7 days before t from an hourly frame (only rows <= t are used)."""
    first, last = week_window(t)
    t0 = datetime.strptime(t, FMT)
    h = hours[hours.index <= t0]
    full = pd.date_range(datetime.combine(first, datetime.min.time()) - timedelta(hours=8), datetime.combine(last, datetime.min.time()) + timedelta(hours=23),
                         freq="h")
    h = h.reindex(full)                                                            # missing hours -> NaN (never filled)
    r8 = {p: h[p].rolling(8, min_periods=MIN_8H_HOURS).mean() for p in ("o3", "co")}
    days = []
    for d in pd.date_range(first, last, freq="D"):
        sl = slice(d, d + timedelta(hours=23))
        day = h.loc[sl]
        vals, n = {}, {}
        for p in POLL:
            n[p] = int(day[p].notna().sum())
        for p in ("pm25", "pm10", "no2", "so2"):
            vals[p] = float(day[p].mean()) if n[p] >= MIN_DAY_HOURS else None
        for p in ("o3", "co"):
            mx = r8[p].loc[sl].max()
            vals[p] = float(mx) if n[p] >= MIN_DAY_HOURS and pd.notna(mx) else None
        co24 = float(day["co"].mean()) if n["co"] >= MIN_DAY_HOURS else None
        aqi_arr, si = aq_clean.aqi_from_averages({p: np.array([np.nan if vals[p] is None else vals[p]]) for p in POLL})
        aqi = None if np.isnan(aqi_arr[0]) else adv.rint(aqi_arr[0])
        sis = {p: (None if np.isnan(si[p][0]) else float(si[p][0])) for p in POLL}
        dom = max((p for p in POLL if sis[p] is not None), key=lambda p: sis[p], default=None) if aqi is not None else None
        days.append({"date": d.strftime("%Y-%m-%d"), "label": f"{d.day} {adv.MONTHS[d.month - 1]}", "weekday": d.strftime("%a"),
                     "aqi": aqi, "category": adv.category_of(aqi) if aqi is not None else None, "dominant": dom, "valid": aqi is not None,
                     "values": {p: (None if vals[p] is None else round(vals[p], 3 if p == "co" else 1)) for p in POLL},
                     "co_24h": None if co24 is None else round(co24, 3), "si": sis, "hours": n})
    return days


def analyse(days):
    valid = [d for d in days if d["valid"]]
    out = {"days": days, "valid_days": len(valid), "enough": len(valid) >= MIN_VALID_DAYS}
    exc = []
    for p in POLL:
        vals = [(d["co_24h"] if p == "co" else d["values"][p]) for d in days]
        india = [d["values"][p] for d in days]
        exc.append({"pollutant": p, "name": adv.pname(p), "unit": UNITS[p],
                    "india_limit": NAAQS[p], "india_avg": NAAQS_AVG[p], "who_level": WHO[p], "who_avg": WHO_AVG[p],
                    "days_with_data": sum(v is not None for v in india),
                    "days_above_india": sum(v is not None and v > NAAQS[p] for v in india),
                    "days_above_who": sum(v is not None and v > WHO[p] for v in vals), "days_with_data_who": sum(v is not None for v in vals)})
    out["exceedances"] = exc
    # trend: mean AQI of the last 3 days vs the previous 4 (valid days only; at least 2 in each part)
    last3 = [d["aqi"] for d in days[-3:] if d["valid"]]
    prev4 = [d["aqi"] for d in days[:4] if d["valid"]]
    if len(last3) >= 2 and len(prev4) >= 2:
        a, b = float(np.mean(last3)), float(np.mean(prev4))
        thr = max(TREND_ABS, TREND_REL * b)
        out["trend"] = {"direction": "rising" if a - b > thr else ("falling" if b - a > thr else "steady"), "last3": round(a), "prev4": round(b)}
    else:
        out["trend"] = {"direction": "unknown"}
    cnt = Counter(d["dominant"] for d in valid if d["dominant"])
    if cnt:
        top = max(cnt.values())
        tied = [p for p, k in cnt.items() if k == top]
        out["dominant"] = max(tied, key=lambda p: np.mean([d["si"][p] for d in valid if d["si"][p] is not None]))
    else:
        out["dominant"] = None
    out["days_moderate_or_worse"] = sum(d["aqi"] >= PERSIST_AQI for d in valid)
    out["persistent"] = out["days_moderate_or_worse"] >= PERSIST_DAYS
    out["worst_category"] = max((d["category"] for d in valid), key=lambda c: CAT_RANK[c], default=None)
    out["level"] = ("persistent" if out["persistent"] else "episode" if out["days_moderate_or_worse"] > 0 else "clean")
    return out


# ---- advice from the rule table -----------------------------------------------------------------------------------------------------------
def profile_groups(groups):
    """Profile groups -> rule groups: lung, heart, child, older, pregnant, outdoor_work, exercise; healthy if none."""
    g = set(groups or [])
    out = {x for x in ("lung", "heart", "child", "older", "pregnant") if x in g}
    if "outdoor_worker" in g:
        out.add("outdoor_work")
    if "athlete" in g:
        out.add("exercise")
    return out or {"healthy"}


def _applies(rule, an, groups):
    if rule.get("levels") and an["level"] not in rule["levels"]:
        return False
    need = rule.get("min_category_healthy") if ("healthy" in groups and rule.get("min_category_healthy")) else rule.get("min_category")
    if need and (an["worst_category"] is None or CAT_RANK[an["worst_category"]] < CAT_RANK[need]):
        return False
    if rule.get("pollutant") and rule["pollutant"] != an["dominant"]:
        return False
    rg = rule.get("groups", ["all"])
    if "all" not in rg and not (set(rg) & groups):
        return False
    if rule.get("not_groups") and set(rule["not_groups"]) & groups:
        return False
    return True


STALE_AFTER_H = 24          # live: newest observation older than this -> the card describes the LAST AVAILABLE week, not "this week"
PAST = [("This week's", "That week's"), ("this week", "that week")]       # the only present-tense phrases in the rule texts (test S5)


def past_tense(text):
    for a, b in PAST:
        text = text.replace(a, b)
    return text


def health(an, groups_in):
    """{'clean': [...], 'short_term': [...], 'long_term': [...], 'actions': [...]}; each item {id, text, sources}. Empty when not enough data.
    Long-term statements ONLY for persistent weeks (checked here as well as in the rule table)."""
    out = {"clean": [], "short_term": [], "long_term": [], "actions": []}
    if not an["enough"]:
        return out
    groups = profile_groups(groups_in)
    if an["level"] == "clean":
        out["clean"] = [dict(r) for r in RULES["clean"] if _applies(r, an, groups)]
        return out
    for key in ("short_term", "long_term", "actions"):
        items = [r for r in RULES[key] if _applies(r, an, groups)]
        if key == "long_term" and not an["persistent"]:
            items = []
        items.sort(key=lambda r: 0 if "all" in r.get("groups", ["all"]) else 1)
        out[key] = [{"id": r["id"], "text": r["text"], "marked": r["marked"], "sources": r["sources"],
                     **({"icon": adv.icon_for({"text": r["text"], "kind": "action"})} if key == "actions" else {})} for r in items]
    return out


def top3(h):
    """summary (presentation): the ids of the 3 actions shown first - the profile's own actions (rule order), then the general ones."""
    acts = [r for r in RULES["actions"] if r["id"] in {i["id"] for i in h["actions"]}]
    return [r["id"] for r in sorted(acts, key=lambda r: 0 if "all" not in r.get("groups", ["all"]) else 1)][:3]


def _past_health(h):
    return {k: [{**i, "text": past_tense(i["text"]), "marked": past_tense(i.get("marked", i["text"]))} for i in v] for k, v in h.items()}


# ---- entry points --------------------------------------------------------------------------------------------------------------------------
def weekly(db, table, station, t, groups=None, data=None):
    """data: {"mode", "stale", ...}; stale (live data > 24 h old) -> health texts in the past tense ("that week")."""
    data = data or {"mode": "replay", "stale": False}
    first, last = week_window(t)
    start = (datetime.combine(first, datetime.min.time()) - timedelta(hours=8)).strftime(FMT)
    hours = load_hours(db, table, station, start, t)
    an = analyse(summarize(hours, t))
    h = health(an, groups)
    return {**an, "window": {"first": str(first), "last": str(last), "clock": t,
                       "clock_end": (datetime.strptime(t, FMT) + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M")}, "health": _past_health(h) if data["stale"] else h, "top3": top3(h), "data": data,
            "disclaimer": "General information from public health guidance, not medical advice.",
            "notes": {"who": RULES["notes"]["who"], "india": RULES["notes"]["india"]},
            "references": {k: {"text": adv.REFERENCES[k], "url": RULES["urls"].get(k, "")} for k in sorted(adv.REFERENCES, key=int)}}


def replay_weekly(station, t, groups=None):
    return weekly(ROOT / "data" / "replay.db", "replay_obs", station, t, groups)


def live_weekly(station, groups=None, now=None):
    """now: the real clock (IST; default live_api.now_ist, which honours the test override AQI_LIVE_NOW). Age = now - END of the newest PM hour
    (hours are labelled by their start, as on the live page)."""
    with sqlite3.connect(ROOT / "data" / "aqi.db", timeout=30) as c:
        row = c.execute("SELECT MAX(datetime) FROM hourly WHERE station=? AND (pm25 IS NOT NULL OR pm10 IS NOT NULL)", (station,)).fetchone()
    if not row or not row[0]:
        return None
    if now is None:
        import live_api
        now = live_api.now_ist()
    end = datetime.strptime(row[0], FMT) + timedelta(hours=1)
    age = (now - end).total_seconds() / 3600
    data = {"mode": "live", "newest_end": end.strftime("%Y-%m-%d %H:%M"), "now": now.strftime("%Y-%m-%d %H:%M"), "age_hours": round(age, 1),
            "stale": age > STALE_AFTER_H}
    return weekly(ROOT / "data" / "aqi.db", "hourly", station, row[0], groups, data)
