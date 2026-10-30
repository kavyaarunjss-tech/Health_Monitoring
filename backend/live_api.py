"""Live mode API (OpenAQ data in data/aqi.db + forecasts from forecast_live.py).

Every forecast is labelled by its EFFECTIVE horizon = hours after the newest observation (the data age is shown separately, because
OpenAQ delivers with a delay). Forecasts whose target time has already passed are marked 'past'. Persistence fallback is always labelled.
"""
import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException

import advice as adv

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "aqi.db"
FMT = "%Y-%m-%d %H:%M:%S"
IST = timezone(timedelta(hours=5, minutes=30))
_R = json.loads((Path(__file__).resolve().parent / "ranges.json").read_text(encoding="utf-8"))
MODEL_RANGES, PERS_RANGES = _R["ranges"], _R["persistence_ranges"]
STATIONS = {"silkboard": "Silk Board, Bengaluru", "hebbal": "Hebbal, Bengaluru", "jayanagar": "Jayanagar 5th Block, Bengaluru",
            "chikkaballapura": "Chikkaballapur Rural", "chikkamagaluru": "Kalyana Nagara, Chikkamagaluru",
            "mysuru": "Hebbal 1st Stage, Mysuru", "ramanagara": "Vijay Nagar, Ramanagara", "madikeri": "Stuart Hill, Madikeri"}
router = APIRouter(prefix="/api/live")

POLLUTANTS = [("pm25", "PM2.5", "\u00b5g/m\u00b3", "24 h"), ("pm10", "PM10", "\u00b5g/m\u00b3", "24 h"), ("no2", "NO\u2082", "\u00b5g/m\u00b3", "24 h"),
              ("so2", "SO\u2082", "\u00b5g/m\u00b3", "24 h"), ("o3", "O\u2083", "\u00b5g/m\u00b3", "8 h"), ("co", "CO", "mg/m\u00b3", "8 h")]


def pollutants_from(row):
    """Current hourly concentrations and CPCB sub-indices (computed from the 24 h / 8 h running averages) of one observed hour."""
    if not row:
        return None
    out = []
    for key, label, unit, window in POLLUTANTS:
        val, si, avg = row.get(key), row.get(key + "_si"), row.get(key + "_avg")
        out.append({"key": key, "label": label, "unit": unit, "window": window,
                    "value": None if val is None else round(float(val), 2 if key == "co" else 1),        # hourly value
                    "avg": None if avg is None else round(float(avg), 3 if key == "co" else 2),          # the 24 h / 8 h average the sub-index comes from
                    "si": None if si is None else adv.rint(si),
                    "category": None if si is None else adv.category_of(si)})
    return out



def q(sql, args=()):
    with sqlite3.connect(DB, timeout=30) as con:
        con.row_factory = sqlite3.Row
        return [dict(r) for r in con.execute(sql, args)]


def now_ist():
    fake = os.environ.get("AQI_LIVE_NOW")             # TESTS ONLY: pretend the clock is "YYYY-MM-DD HH:MM" (IST) to test fresh / partly-passed / all-passed cases
    if fake:
        return datetime.strptime(fake, "%Y-%m-%d %H:%M")
    return datetime.now(IST).replace(tzinfo=None)


def severity(age_h):
    return "fresh" if age_h <= 3 else ("delayed" if age_h <= 24 else "stale")


def tier_of(h):
    return "high" if h <= 6 else ("medium" if h <= 24 else "low")


def band(a):
    return "low" if a < 60 else ("mid" if a < 100 else "high")


def end_str(label):
    return (label + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M")


@router.get("/stations")
def stations():
    now, out = now_ist(), []
    fc = {r["station"]: r for r in q("SELECT station, origin, method, generated_at, persistence FROM live_forecast GROUP BY station")}
    for st, name in STATIONS.items():
        r = fc.get(st)
        if r is None:
            out.append({"id": st, "name": name, "status": "none"})
            continue
        origin = datetime.strptime(r["origin"], FMT)
        age = (now - (origin + timedelta(hours=1))).total_seconds() / 3600
        aqi = adv.rint(r["persistence"]) if r["persistence"] is not None else None              # the newest observed AQI (forecast origin)
        out.append({"id": st, "name": name, "last_obs_end": end_str(origin), "age_hours": round(age, 1), "status": severity(age),
                    "aqi": aqi, "category": adv.category_of(aqi) if aqi is not None else None})
    return out


@router.get("/state")
def state(station: str):
    if station not in STATIONS:
        raise HTTPException(404, "unknown station")
    rows = q("SELECT * FROM live_forecast WHERE station=? ORDER BY horizon", (station,))
    if not rows:
        return {"mode": "LIVE", "station": station, "station_name": STATIONS[station], "severity": "none",
                "warnings": ["No valid AQI observation in the last 7 days for this station: no forecast can be made."],
                "forecasts": [], "observed": []}
    now = now_ist()
    origin = datetime.strptime(rows[0]["origin"], FMT)
    last_end = origin + timedelta(hours=1)
    age = (now - last_end).total_seconds() / 3600
    sev = severity(age)
    obs = q("SELECT datetime, AQI FROM hourly WHERE station=? AND datetime<=? AND datetime>=? AND AQI IS NOT NULL ORDER BY datetime",
            (station, origin.strftime(FMT), (origin - timedelta(hours=95)).strftime(FMT)))
    observed = [{"x": (datetime.strptime(o["datetime"], FMT) + timedelta(hours=1) - last_end).total_seconds() / 3600,
                 "t_end": end_str(datetime.strptime(o["datetime"], FMT)), "aqi": adv.rint(o["AQI"])} for o in obs]
    prow = q("SELECT pm25, pm10, no2, so2, o3, co, pm25_si, pm10_si, no2_si, so2_si, o3_si, co_si, pm25_avg, pm10_avg, no2_avg, so2_avg, o3_avg, co_avg FROM hourly WHERE station=? AND datetime=?",
             (station, origin.strftime(FMT)))
    pollutants = pollutants_from(prow[0] if prow else None)
    fcs, any_fallback = [], False
    for r in rows:
        h = r["horizon"]
        target = origin + timedelta(hours=h)
        lead = (target + timedelta(hours=1) - now).total_seconds() / 3600
        method = r["method"]
        any_fallback |= method != "model"
        a = adv.rint(r["aqi"])
        rng = (MODEL_RANGES if method == "model" else PERS_RANGES)[str(h)][band(a)]
        lo, hi = max(0, adv.rint(a + rng[0])), min(500, adv.rint(a + rng[1]))
        fcs.append({"horizon": h, "target_end": end_str(target), "hours_from_now": round(lead, 1),
                    "status": "past" if lead <= 0 else "future", "aqi": a, "category": adv.category_of(a),
                    "range_low": lo, "range_high": hi, "category_low": adv.category_of(lo), "category_high": adv.category_of(hi),
                    "tier": tier_of(h), "method": method, "dominant": r["dominant"],
                    "label": f"+{h} h after the last observation"})
    warnings = []
    if sev == "stale":
        warnings.append(f"The newest observation is {age:.0f} hours old. The data feed (OpenAQ) is delayed or stopped for this station. "
                        "Everything below starts from that old observation; it is NOT a forecast for right now.")
    elif sev == "delayed":
        warnings.append(f"The newest observation is {age:.0f} hours old (delayed feed).")
    if any_fallback:
        warnings.append("Persistence fallback: no trained forecast model is available, so the forecast is simply the last observed AQI "
                        "(\"AQI stays as it was\"). Persistence has no skill beyond what the last observation already tells.")
    main = [f for f in fcs if f["horizon"] <= 24]                      # the main pages show only +1, +6, +12, +24 h
    past = [f for f in main if f["status"] == "past"]
    if past:
        who = f"All {len(main)} forecast horizons" if len(past) == len(main) else (f"1 of the {len(main)} forecast horizons" if len(past) == 1 else f"{len(past)} of the {len(main)} forecast horizons")
        warnings.append(who + (" (up to 24 h) already lies" if len(past) == 1 else " (up to 24 h) already lie") +
                        " in the past (their target time has passed); no observation has arrived yet to check " + ("it." if len(past) == 1 else "them."))
    return {"mode": "LIVE", "station": station, "station_name": STATIONS[station], "now": now.strftime("%Y-%m-%d %H:%M"),
            "last_obs_end": last_end.strftime("%Y-%m-%d %H:%M"), "age_hours": round(age, 1), "severity": sev,
            "last_aqi": adv.rint(rows[0]["persistence"]), "last_category": adv.category_of(rows[0]["persistence"]),
            "generated_at": rows[0]["generated_at"], "trained_through": rows[0]["trained_through"],
            "warnings": warnings, "observed": observed, "forecasts": fcs, "pollutants": pollutants,
            "dominant_now": (q("SELECT dominant FROM hourly WHERE station=? AND datetime=?", (station, origin.strftime(FMT))) or [{}])[0].get("dominant")}
