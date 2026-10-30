"""FastAPI backend: Replay mode (and later live mode) for the AQI forecast website.

Run (project root, aqi env):
    python -m uvicorn backend.app:app --port 8000
then open http://127.0.0.1:8000

Replay rule: for a simulated time T the API returns only (a) observed data with hour label <= T and (b) forecasts
whose origin is exactly T. True values are returned only for targets whose hour is <= T (already happened).
Time convention: hour labels are hour-START (aq_clean.py); the API also returns hour-END times (+1 h) for display.
"""
import os
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi import Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import advice as adv  # noqa: E402
import diurnal  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "replay.db"
FMT = "%Y-%m-%d %H:%M:%S"

STATIONS = {
    "silkboard": "Silk Board, Bengaluru", "hebbal": "Hebbal, Bengaluru", "jayanagar": "Jayanagar 5th Block, Bengaluru",
    "chikkaballapura": "Chikkaballapur Rural", "chikkamagaluru": "Kalyana Nagara, Chikkamagaluru",
    "mysuru": "Hebbal 1st Stage, Mysuru", "ramanagara": "Vijay Nagar, Ramanagara", "madikeri": "Stuart Hill, Madikeri",
}
PERIODS = {
    "validation": {"label": "Validation period (17 Apr - 29 May 2026): more pollution events; models fitted on training data only",
                   "start": "2026-04-17 07:00:00", "end": "2026-05-29 12:00:00"},
    "test": {"label": "Test period (29 May - 21 Jul 2026): monsoon, few events; the official scored test",
             "start": "2026-05-29 14:00:00", "end": "2026-07-21 23:00:00"},
}
import json  # noqa: E402
RANGES = json.loads((Path(__file__).resolve().parent / "ranges.json").read_text(encoding="utf-8"))["ranges"]
MAIN_HORIZONS = (1, 6, 12, 24)        # research-grade horizons
LOWER_CONF_HORIZONS = (36, 48, 72)    # beyond 24 h: category + trend only, lower confidence
DATA_AGE_HOURS_REPLAY = 0             # replay assumes the newest observation is the simulated "now"

from contextlib import asynccontextmanager  # noqa: E402
import scheduler as sched  # noqa: E402


@asynccontextmanager
async def lifespan(_app):
    sched.start()                       # does nothing unless AQI_SCHEDULER=1
    yield
    sched.shutdown()


app = FastAPI(title="AQI forecast: replay and live API", lifespan=lifespan)
from live_api import router as live_router  # noqa: E402
app.include_router(live_router)
import auth_api  # noqa: E402  (sign-up / login / own profile; data/users.db)
app.include_router(auth_api.router)


def band_of(aqi):
    return "low" if aqi < 60 else ("mid" if aqi < 100 else "high")


def tier_of(effective_h):
    """Confidence tier from the EFFECTIVE horizon = age of the newest observation + forecast lead time (hours).
    Evidence (results/accuracy): high 1-6 h, medium 12-24 h, low 36+ h (no consistent skill over persistence)."""
    if effective_h <= 6:
        return "high"
    return "medium" if effective_h <= 24 else "low"


def likely_range(aqi, h):
    lo, hi, _ = RANGES[str(h)][band_of(aqi)]
    return max(0.0, aqi + lo), min(500.0, aqi + hi)


def q(sql, args=()):
    with sqlite3.connect(DB, timeout=30) as con:
        con.row_factory = sqlite3.Row
        return [dict(r) for r in con.execute(sql, args)]


def end_time(label):
    """Hour-start label -> hour-end display string."""
    return (datetime.strptime(label, FMT) + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M")


def check(period, station):
    if period not in PERIODS:
        raise HTTPException(404, "unknown period")
    if station not in STATIONS:
        raise HTTPException(404, "unknown station")


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


@app.get("/api/stations")
def stations():
    return [{"id": k, "name": v} for k, v in STATIONS.items()]


@app.get("/api/periods")
def periods():
    out = []
    for key, p in PERIODS.items():
        rows = q("SELECT COUNT(*) n, SUM(AQI>100) gt100, SUM(AQI>200) gt200 FROM replay_obs "
                 "WHERE datetime BETWEEN ? AND ? AND AQI IS NOT NULL", (p["start"], p["end"]))[0]
        out.append({"key": key, **p, "valid_hours": rows["n"], "hours_gt100": rows["gt100"], "hours_gt200": rows["gt200"]})
    default = max(out, key=lambda r: (r["hours_gt200"] or 0, r["hours_gt100"] or 0))["key"]
    return {"default": default, "periods": out}


@app.get("/api/replay/hours")
def hours(period: str, station: str):
    """All simulated hours (labels) of a period that have forecasts at this station."""
    check(period, station)
    p = PERIODS[period]
    rows = q("SELECT DISTINCT origin FROM replay_fc WHERE period=? AND station=? AND origin BETWEEN ? AND ? ORDER BY origin",
             (period, station, p["start"], p["end"]))
    return {"hours": [r["origin"] for r in rows]}


def find_onsets(rows, level):
    """Pollution-event ONSETS in a series of observed (hour label, integer AQI) rows, for the 'skip to next pollution event' demo shortcut.
    An onset is an hour t whose previous hour is also observed and where
      * the AQI reaches the user's alert level from below  (AQI(t-1) < level <= AQI(t); the same 'reaches' rule the alerts use), or
      * the CPCB category rises to Moderate or worse (e.g. Moderate -> Poor, Poor -> Very Poor).
    A rise that merely continues inside an episode, or a Good <-> Satisfactory flicker, is not an onset."""
    out, prev = [], None
    for t, a in rows:
        a = adv.rint(a)
        if prev is not None and datetime.strptime(t, FMT) - datetime.strptime(prev[0], FMT) == timedelta(hours=1):
            pa = prev[1]
            ci, cp = adv.ORDER.index(adv.category_of(a)), adv.ORDER.index(adv.category_of(pa))
            by_level, by_cat = pa < level <= a, (ci > cp and ci >= 2)
            if by_level or by_cat:
                out.append({"t": t, "kind": "level and category" if (by_level and by_cat) else ("level" if by_level else "category"),
                            "from": pa, "to": a, "cat_from": adv.category_of(pa), "cat_to": adv.category_of(a)})
        prev = (t, a)
    return out


@app.get("/api/replay/events")
def events(period: str, station: str, alert_from: int = 101):
    """Onsets of pollution events in a period for the demo shortcut (it looks ahead; it is not part of any forecast)."""
    check(period, station)
    p = PERIODS[period]
    start = (datetime.strptime(p["start"], FMT) - timedelta(hours=1)).strftime(FMT)      # the hour before the period, to judge the first hour
    rows = q("SELECT datetime, AQI FROM replay_obs WHERE station=? AND datetime BETWEEN ? AND ? AND AQI IS NOT NULL ORDER BY datetime",
             (station, start, p["end"]))
    return {"alert_level": alert_from, "onsets": [o for o in find_onsets([(r["datetime"], r["AQI"]) for r in rows], alert_from)
                                                  if o["t"] >= p["start"]]}


@app.get("/api/replay/state")
def state(period: str, station: str, t: str, groups: str = "", alert_from: int = 201):
    check(period, station)
    try:
        datetime.strptime(t, FMT)
    except ValueError:
        raise HTTPException(400, "t must be 'YYYY-MM-DD HH:MM:SS'")
    t0 = datetime.strptime(t, FMT)
    since = (t0 - timedelta(hours=47)).strftime(FMT)
    obs = q("SELECT datetime, AQI, category, dominant FROM replay_obs WHERE station=? AND datetime BETWEEN ? AND ? "
            "ORDER BY datetime", (station, since, t))
    observed = [{"t_end": end_time(r["datetime"]), "aqi": r["AQI"], "category": r["category"]} for r in obs]
    now = obs[-1] if obs and obs[-1]["datetime"] == t else None
    prow = q("SELECT pm25, pm10, no2, so2, o3, co, pm25_si, pm10_si, no2_si, so2_si, o3_si, co_si, pm25_avg, pm10_avg, no2_avg, so2_avg, o3_avg, co_avg FROM replay_obs WHERE station=? AND datetime=?", (station, t))
    pollutants = pollutants_from(prow[0] if prow else None)
    fcs = q("SELECT horizon, ensemble, persistence, huber, dominant FROM replay_fc "
            "WHERE period=? AND station=? AND origin=? ORDER BY horizon", (period, station, t))
    have = {r["horizon"]: r for r in fcs}
    forecasts = []
    for h in MAIN_HORIZONS + LOWER_CONF_HORIZONS:          # always all horizons; unavailable ones are flagged
        target = (t0 + timedelta(hours=h)).strftime(FMT)
        base = {"horizon": h, "target_end": end_time(target), "tier": tier_of(h + DATA_AGE_HOURS_REPLAY),
                "confidence": "main" if h in MAIN_HORIZONS else "lower"}
        r = have.get(h)
        if r is None:
            forecasts.append({**base, "available": False})
            continue
        lo, hi = likely_range(r["ensemble"], h)
        a, lo_i, hi_i = adv.rint(r["ensemble"]), adv.rint(lo), adv.rint(hi)
        forecasts.append({**base, "available": True, "aqi": a, "aqi_raw": round(r["ensemble"], 1),
                          "range_low": lo_i, "range_high": hi_i,
                          "category": adv.category_of(a), "category_low": adv.category_of(lo_i),
                          "category_high": adv.category_of(hi_i),
                          "persistence": adv.rint(r["persistence"]), "huber": adv.rint(r["huber"]), "dominant": r["dominant"]})
    # forecasts made earlier whose target hour is exactly t (now realised): the only place a true value is shown
    realised = []
    for h in MAIN_HORIZONS + LOWER_CONF_HORIZONS:
        origin = (t0 - timedelta(hours=h)).strftime(FMT)
        rr = q("SELECT ensemble, persistence, y_true FROM replay_fc WHERE period=? AND station=? AND origin=? AND horizon=?",
               (period, station, origin, h))
        if rr:
            realised.append({"horizon": h, "made_at_end": end_time(origin), "forecast": adv.rint(rr[0]["ensemble"]),
                             "persistence": adv.rint(rr[0]["persistence"]), "actual": adv.rint(rr[0]["y_true"])})
    # advice for the same response (so the page needs no second round trip that could belong to an older hour)
    prof = {"groups": [g for g in groups.split(",") if g], "alert_from": alert_from}
    next24 = [f for f in forecasts if f.get("available") and f["confidence"] == "main"]
    peak = max(next24, key=lambda f: f["aqi"]) if next24 else None
    now_aqi = adv.rint(now["AQI"]) if now is not None and now["AQI"] is not None else None
    basis = None
    if peak and (now_aqi is None or peak["aqi"] >= now_aqi):
        basis = {"aqi": peak["aqi"], "label": f"the forecast for +{peak['horizon']} h (hour ending {peak['target_end']})"}
    elif now_aqi is not None:
        basis = {"aqi": now_aqi, "label": "the current observed AQI"}
    advice_out = None if basis is None else {**adv.advice(basis["aqi"], prof), "basis": basis}
    # personalised advice from parts (profile groups, trend, typical cleanest time of day at this station from the 28 days up to t, main pollutant,
    # tip chosen by the alert number = issue hour, so the same alert always shows the same tip); used by the "For you" line, the Health advice
    # tab and the alert pop-up
    now_dom = now["dominant"] if now is not None else None
    dom = (peak.get("dominant") if (basis and peak and basis["aqi"] == peak["aqi"]) else now_dom) or now_dom
    personal = None if basis is None else {**adv.personal_advice(basis["aqi"], prof, next24, now_aqi, dom, adv.alert_number(t),
                                                                 diurnal.replay_profile(station, t)), "basis": basis}
    return {"mode": "REPLAY", "advice": advice_out, "personal": personal, "pollutants": pollutants, "station": station, "station_name": STATIONS[station], "period": period,
            "sim_time_end": end_time(t), "label_time": t,
            "now": None if now is None else {"aqi": now["AQI"], "category": now["category"], "dominant": now["dominant"]},
            "observed": observed, "forecasts": forecasts, "realised": realised}


@app.get("/api/stations/now")
def stations_now(mode: str = "replay", t: str = ""):
    """'All stations now' card: each station's newest observed AQI. Replay: at the replay clock t (newest valid hour <= t within 24 h; age relative
    to t). Live: the newest observation of each station with its age relative to now. status: fresh (<= 3 h), delayed (<= 24 h), stale (> 24 h), none."""
    if mode == "live":
        import live_api
        rows = live_api.stations()
        return {"mode": "live", "clock": live_api.now_ist().strftime("%Y-%m-%d %H:%M"),
                "stations": [{"id": r["id"], "name": r["name"], "aqi": r.get("aqi"), "category": r.get("category"), "obs_end": r.get("last_obs_end"),
                              "age_hours": r.get("age_hours"), "status": r["status"] if r.get("aqi") is not None else "none"} for r in rows]}
    try:
        tt = datetime.strptime(t, FMT)
    except ValueError:
        raise HTTPException(400, "t must be 'YYYY-MM-DD HH:MM:SS'")
    lo = (tt - timedelta(hours=24)).strftime(FMT)
    out = []
    for st, name in STATIONS.items():
        r = q("SELECT datetime, AQI FROM replay_obs WHERE station=? AND datetime<=? AND datetime>=? AND AQI IS NOT NULL ORDER BY datetime DESC LIMIT 1",
              (st, t, lo))
        if not r:
            out.append({"id": st, "name": name, "aqi": None, "category": None, "obs_end": None, "age_hours": None, "status": "none"})
            continue
        dt = datetime.strptime(r[0]["datetime"], FMT)
        age = (tt - dt).total_seconds() / 3600
        aqi = adv.rint(r[0]["AQI"])
        out.append({"id": st, "name": name, "aqi": aqi, "category": adv.category_of(aqi), "obs_end": (dt + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M"),
                    "age_hours": round(age, 1), "status": "fresh" if age <= 3 else ("delayed" if age <= 24 else "stale")})
    return {"mode": "replay", "clock": t, "clock_end": (tt + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M"), "stations": out}


@app.get("/api/weekly")
def weekly_summary(station: str, mode: str = "replay", t: str = "", groups: str = ""):
    """'This week's air and your health': 7 complete days before the replay clock t (replay) or the newest observation (live).
    Only hours <= t are read. Health text only from weekly_advice_rules.json (sources in docs/health_advisory_reference.md section 8)."""
    import weekly
    if station not in STATIONS:
        raise HTTPException(404, "unknown station")
    g = [x for x in groups.split(",") if x]
    if mode == "live":
        out = weekly.live_weekly(station, g)
        if out is None:
            raise HTTPException(404, "no live data for this station")
        return out
    try:
        datetime.strptime(t, FMT)
    except ValueError:
        raise HTTPException(400, "t must be 'YYYY-MM-DD HH:MM:SS'")
    return weekly.replay_weekly(station, t, g)


class Profile(BaseModel):
    groups: list[str] = []
    alert_from: int = 101
    forecasts: list[dict] = []          # optional: +1..+24 h forecasts (horizon, aqi, target_end, available, status) for the trend
    now_aqi: float | None = None
    dominant: str | None = None
    station: str | None = None          # live page: station and the newest observation (hour ending "YYYY-MM-DD HH:MM") for the typical
    last_obs_end: str | None = None     # time-of-day pattern (data up to that hour) and the alert number of the tip


@app.post("/api/advice")
def advice_for(profile: Profile, aqi: float = Query(...)):
    p = profile.model_dump()
    pattern, seq = None, 0
    if p["station"] in STATIONS and p["last_obs_end"]:
        try:
            label = (datetime.strptime(p["last_obs_end"][:16], "%Y-%m-%d %H:%M") - timedelta(hours=1)).strftime(FMT)
            pattern, seq = diurnal.live_profile(p["station"], label), adv.alert_number(label)
        except ValueError:
            pass
    return {**adv.advice(aqi, p), "personal": adv.personal_advice(aqi, p, p["forecasts"], p["now_aqi"], p["dominant"], seq, pattern)}


@app.get("/api/meta")
def meta():
    return {"disclaimer": adv.DISCLAIMER, "references": adv.REFERENCES, "default_alert": adv.DEFAULT_ALERT,
            "everyone_alert": adv.EVERYONE_ALERT, "categories": [c for _, c in adv.CATEGORIES]}



# ----------------------------------------------------------------------------- e-mail alerts and local profile (see notify_email.py)
import notify_email as ne  # noqa: E402
import notify_twilio as ntw  # noqa: E402



class ProfileIn(BaseModel):
    groups: list[str] = []
    station: str = "silkboard"
    alert_from: int = 101
    email: str = ""


@app.get("/api/profile")
def get_profile():
    p = ne.load_profile()
    return {**p, "email_configured": ne.configured()}


@app.post("/api/profile")
def post_profile(p: ProfileIn):
    """Stores ONLY groups, station, alert_from, email in data/profile.json (local, git-ignored)."""
    try:
        return {**ne.save_profile(p.model_dump()), "email_configured": ne.configured()}
    except ValueError as e:
        raise HTTPException(400, str(e))


class ReplayMailIn(BaseModel):
    period: str
    station: str
    t: str
    escalation: str = ""            # "", "category" (higher category) or "level" (possible -> likely, same category)


@app.post("/api/email/replay-alert", dependencies=[Depends(auth_api.same_origin)])
def email_replay_alert(m: ReplayMailIn, user=Depends(auth_api.optional_user)):
    """QUEUE the alert e-mail that a replay hour would trigger (subject starts with [REPLAY DEMO]). The outbox worker sends it when a real-time
    rate-limit slot is free (1 per 60 s, 10 per hour), highest priority first (escalation, then category); it is never dropped by the limit.
    Logged in: uses the account's own profile and goes to the account's own (confirmed) address, only if "replay-demo e-mails" is on.
    Guest: uses data/profile.json and its e-mail (or ALERT_EMAIL_TO), as before."""
    check(m.period, m.station)
    if user is None:                                       # guest: e-mail only, as before
        if not ne.configured():
            raise HTTPException(503, "E-mail is not configured (.env needs GMAIL_ADDRESS, GMAIL_APP_PASSWORD, ALERT_EMAIL_TO)")
        try:
            return ne.replay_enqueue(m.station, m.t, m.period, escalation=m.escalation)
        except Exception as e:  # report the type only, never credentials
            raise HTTPException(502, f"E-mail could not be queued ({type(e).__name__})")
    # account: e-mail (confirmed address) and/or WhatsApp (number), as switched on in the profile; one channel failing never blocks the other
    import notify_push as npu
    want_mail, want_wa = bool(user["replay_emails"]), bool(user["replay_whatsapp"] and user["whatsapp"])
    want_push = bool(auth_api.users.push_subs(user["id"], "replay"))
    if not want_mail and not want_wa and not want_push:
        raise HTTPException(403, "Replay-demo alerts are off in your profile.")
    if want_mail and not user["email_verified"] and not want_wa and not want_push:
        raise HTTPException(403, "Please confirm your e-mail address first (see your profile page).")
    push_ok = want_push and (npu.configured() or npu.FAKE)
    if (not want_mail or not ne.configured()) and (not want_wa or not ntw.configured()) and not push_ok:
        raise HTTPException(503, "Neither e-mail, WhatsApp nor push notifications are configured on this computer (.env).")
    pub = auth_api.users.public(user)
    prof, owner = {"groups": pub["groups"], "alert_from": pub["alert_effective"], "station": pub["station"], "email": user["email"]}, user["id"]
    out = {}
    if want_mail and user["email_verified"] and ne.configured():
        try:
            out = ne.replay_enqueue(m.station, m.t, m.period, escalation=m.escalation, profile=prof, owner=owner)
        except Exception as e:  # report the type only, never credentials
            out = {"queued": False, "reason": f"E-mail could not be queued ({type(e).__name__})"}
    if want_wa and ntw.configured():
        try:
            out["whatsapp"] = ne.replay_enqueue_whatsapp(m.station, m.t, m.period, user["whatsapp"], prof, owner, escalation=m.escalation)
        except Exception as e:
            out["whatsapp"] = {"queued": False, "reason": f"WhatsApp could not be queued ({type(e).__name__})"}
        if "queued" not in out:                            # WhatsApp only: report its result at the top level too
            out.update({k: v for k, v in out["whatsapp"].items() if k in ("queued", "duplicate", "reason", "pending", "subject")})
    if push_ok:
        try:
            out["push"] = ne.replay_enqueue_push(m.station, m.t, m.period, prof, owner, escalation=m.escalation)
        except Exception as e:
            out["push"] = {"queued": False, "reason": f"Push could not be queued ({type(e).__name__})"}
        if "queued" not in out:                            # push only: report its result at the top level too
            out.update({k: v for k, v in out["push"].items() if k in ("queued", "duplicate", "reason", "pending", "subject")})
    return out


@app.get("/api/email/outbox")
def email_outbox(user=Depends(auth_api.optional_user)):
    """Subjects of pending / sent / dropped replay-demo e-mails of this server process (no bodies, no health data): a logged-in user sees
    only their own e-mails, a guest only the guest e-mails."""
    return ne.OUTBOX.status(owner=None if user is None else user["id"])


@app.get("/api/scheduler/status")
def scheduler_status():
    return sched.status()


@app.post("/api/scheduler/run-now")
def scheduler_run_now(request: Request, kind: str = "hourly"):
    """Run an update now (only when the scheduler is enabled). Refused while another update is running. Only from this computer, never
    through a tunnel."""
    if not is_local(request):
        raise HTTPException(403, "Only available on the server computer itself.")
    if not sched.status()["enabled"]:
        raise HTTPException(409, "The scheduler is not enabled (start the server with AQI_SCHEDULER=1)")
    if kind not in ("hourly", "daily"):
        raise HTTPException(400, "kind must be 'hourly' or 'daily'")
    res = {}

    def go():
        res.update(sched.run_job(kind, "manual"))

    if sched.status()["running"]:
        return {"started": False, "reason": "an update is already running"}
    threading.Thread(target=go, daemon=True).start()
    time.sleep(0.2)                     # let the job claim the lock so a second click is refused
    return {"started": True}


@app.middleware("http")
async def no_stale_files(request, call_next):
    """Static pages, scripts and styles get 'Cache-Control: no-cache': the browser must ask the server before reusing its copy (answered with a
    304 when unchanged). Without it browsers reused an old account.js with a newer profile.html (20 Oct 2026: 'Could not load ... textContent')."""
    resp = await call_next(request)
    if not request.url.path.startswith("/api/") and "cache-control" not in resp.headers:
        resp.headers["Cache-Control"] = "no-cache"
    return resp


GUEST_COOKIE = "aqi_guest"
PROXY_HEADERS = ("x-forwarded-for", "x-forwarded-host", "x-forwarded-proto", "cf-connecting-ip", "cf-ray", "x-real-ip", "forwarded")


def is_local(request: Request):
    """True only for a request made directly on this computer (http://127.0.0.1 / localhost). Requests through a tunnel (Cloudflare, ngrok)
    also arrive from 127.0.0.1 but carry proxy headers: they are NOT local. Test-only switches (?selftest=...) and admin actions need this."""
    host = (request.client.host if request.client else "") or ""
    if host not in ("127.0.0.1", "::1", "localhost", "testclient"):
        return False
    if any(h in request.headers for h in PROXY_HEADERS):
        return False
    return request.headers.get("host", "").split(":")[0] in ("127.0.0.1", "localhost", "testserver", "[::1]")


def gated_page(request: Request, file, path):
    """Login first: the replay and live pages need a logged-in user or the guest choice ("Try the demo without an account", /?guest=1, which
    sets a browser-session cookie). Developer self-tests (?selftest=...) are let through so the headless UI tests keep running as guests."""
    q = request.query_params
    guest = q.get("guest") == "1" or request.cookies.get(GUEST_COOKIE) == "1"
    if auth_api.optional_user(request) is None and not guest and not ("selftest" in q and is_local(request)):
        return RedirectResponse("/login.html?next=" + path, status_code=303, headers={"Cache-Control": "no-store"})
    resp = FileResponse(ROOT / "frontend" / file, headers={"Cache-Control": "no-store"})
    if q.get("guest") == "1":
        resp.set_cookie(GUEST_COOKIE, "1", samesite="lax", path="/", httponly=True,      # no max_age: ends when the browser closes
                        secure=request.url.scheme == "https")
    return resp


@app.get("/")
def index(request: Request):
    return gated_page(request, "index.html", "/")


@app.get("/index.html")
def index_html(request: Request):
    return gated_page(request, "index.html", "/")


@app.get("/live.html")
def live_html(request: Request):
    return gated_page(request, "live.html", "/live.html")


import mimetypes  # noqa: E402
mimetypes.add_type("font/woff2", ".woff2")      # bundled Inter font (frontend/fonts/); Windows has no default type for .woff2
# Optional host allow-list for a public tunnel (README "Phone testing over HTTPS"): AQI_ALLOWED_HOSTS="localhost,127.0.0.1,*.trycloudflare.com"
if os.environ.get("AQI_ALLOWED_HOSTS"):
    from starlette.middleware.trustedhost import TrustedHostMiddleware
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=[h.strip() for h in os.environ["AQI_ALLOWED_HOSTS"].split(",") if h.strip()])

app.mount("/", StaticFiles(directory=ROOT / "frontend"), name="static")
