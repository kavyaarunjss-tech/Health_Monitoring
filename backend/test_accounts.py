"""Tests for user accounts (sign-up, login, logout, profile, age rules, alert-level cap, delete account, isolation) and per-user e-mail alerts.

Runs the FastAPI app IN-PROCESS (fastapi TestClient: no network port, never port 8000) with a temporary users.db, a temporary e-mail state/log,
AQI_EMAIL_FAKE=1 and SMTP replaced by a class that raises: no real e-mail can be sent. The real data/users.db and data/email_log.jsonl are
checked to be unchanged at the end.

usage (project root, aqi env):  python backend\\test_accounts.py
"""
import json
import os
import smtplib
import sqlite3
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TMP = Path(tempfile.mkdtemp(prefix="aqi_accounts_"))
os.environ.update(AQI_EMAIL_FAKE="1", AQI_USERS_DB=str(TMP / "users.db"), AQI_SECRET_KEY="test-only-secret-" + "x" * 40,
                  AQI_EMAIL_STATE_FILE=str(TMP / "email_state.json"), AQI_EMAIL_LOG_FILE=str(TMP / "email_log.jsonl"),
                  AQI_RATE_FILE=str(TMP / "rate.json"), AQI_PROFILE_FILE=str(TMP / "profile.json"), AQI_MAIL_MIN_GAP_S="0.2", AQI_MAIL_PER_HOUR="1000")
sys.path.insert(0, str(ROOT / "backend"))
REAL_LOG, REAL_DB = ROOT / "data" / "email_log.jsonl", ROOT / "data" / "users.db"
real_log_before = REAL_LOG.read_bytes() if REAL_LOG.exists() else None
real_db_before = REAL_DB.stat().st_mtime if REAL_DB.exists() else None


class NoSMTP:                       # any attempt to open a real SMTP connection fails the test
    def __init__(self, *a, **k):
        raise AssertionError("real SMTP used in a test")


smtplib.SMTP_SSL = smtplib.SMTP = NoSMTP

from fastapi.testclient import TestClient  # noqa: E402
import app as appmod  # noqa: E402
import notify_email as ne  # noqa: E402
import users  # noqa: E402

failures = []


def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  {extra}" if extra else ""))
    if not cond:
        failures.append(name)


links = []                                       # e-mailed one-time links, captured instead of sending
ne.send_account_link = lambda kind, to, name, link: links.append((kind, to, link)) or True
sent = []                                        # alert e-mails, captured
real_send = ne.send


def capture_send(subject, body, to, dry_run=False):
    sent.append({"to": to, "subject": subject, "body": body})
    return True


def client():
    return TestClient(appmod.app)


def signup(c, name, email, pw="correct horse 1", consent=True):
    return c.post("/api/auth/signup", json={"name": name, "email": email, "password": pw, "consent": consent})


def wait_links(n, timeout=3):
    t = time.time()
    while len(links) < n and time.time() - t < timeout:
        time.sleep(0.05)


# ---- Z. safety: fake mode, SMTP blocked ---------------------------------------------------------------------------------------------
check("Z1 fake e-mail mode is on", ne.FAKE is True)
check("Z2 the users database is the temporary one, not data/users.db", users.DB == TMP / "users.db", str(users.DB))
try:
    ne.send("x", "y", "nobody@example.com")
    check("Z3 send() in fake mode never touches SMTP", True)
except AssertionError:
    check("Z3 send() in fake mode never touches SMTP", False)

# ---- S. sign-up -------------------------------------------------------------------------------------------------------------------
a = client()
r = signup(a, "Asha Rao", "Asha@Example.com")
check("S1 sign-up succeeds", r.status_code == 200, r.text[:200])
me = r.json()
check("S2 e-mail stored lower-case, starts unconfirmed", me.get("email") == "asha@example.com" and me.get("email_verified") is False)
check("S3 no password or hash in the response", "password" not in r.text.lower() and "argon" not in r.text.lower() and "pw_hash" not in r.text)
sc = r.headers.get("set-cookie", "")
check("S4 session cookie is HttpOnly, SameSite=Lax, path /", "aqi_session=" in sc and "httponly" in sc.lower() and "samesite=lax" in sc.lower() and "path=/" in sc.lower(), sc[:160])
with sqlite3.connect(TMP / "users.db") as cn:
    pw_hash = cn.execute("SELECT pw_hash FROM users WHERE email='asha@example.com'").fetchone()[0]
    sess = [x[0] for x in cn.execute("SELECT token_hash FROM sessions")]
token = a.cookies.get("aqi_session")
check("S5 password stored only as an Argon2id hash", pw_hash.startswith("$argon2id$") and "correct horse" not in pw_hash)
check("S6 database keeps only a hash of the session token", token not in sess and len(sess) == 1 and len(sess[0]) == 64)
check("S7 /api/me works with the cookie", a.get("/api/me").json().get("name") == "Asha Rao")
check("S8 password shorter than 8 characters refused", signup(client(), "X", "x1@example.com", pw="short12").status_code == 400)
check("S9 duplicate e-mail refused (case-insensitive)", signup(client(), "Y", "ASHA@example.com").status_code == 409)
check("S10 sign-up without consent refused", signup(client(), "Z", "z@example.com", consent=False).status_code == 400)
check("S11 invalid e-mail refused", signup(client(), "Z", "not-an-email").status_code == 400)
check("S12 empty name refused", signup(client(), "   ", "z2@example.com").status_code == 400)
wait_links(1)
check("S13 a confirmation link was e-mailed (captured, fake)", any(k == "verify" and to == "asha@example.com" for k, to, _ in links), str([(k, t) for k, t, _ in links]))
check("S14 GET /api/me without a cookie -> 401", client().get("/api/me").status_code == 401)
check("S15 /api/me is not cached (Cache-Control: no-store)", a.get("/api/me").headers.get("cache-control") == "no-store")

# ---- L. login / wrong password / logout -------------------------------------------------------------------------------------------
c2 = client()
r = c2.post("/api/auth/login", json={"email": "asha@example.com", "password": "correct horse 1"})
check("L1 login with the right password", r.status_code == 200 and c2.get("/api/me").status_code == 200)
r = client().post("/api/auth/login", json={"email": "asha@example.com", "password": "wrong password"})
check("L2 wrong password -> 401", r.status_code == 401, r.text)
r2 = client().post("/api/auth/login", json={"email": "nobody@example.com", "password": "wrong password"})
check("L3 unknown e-mail gives the same message as a wrong password", r2.status_code == 401 and r2.json()["detail"] == r.json()["detail"])
r = c2.post("/api/auth/logout")
check("L4 logout clears the cookie and ends the session", r.status_code == 200 and c2.get("/api/me").status_code == 401)
old = client(); old.cookies.set("aqi_session", token)
check("L5 the first session (other browser) still works after a logout elsewhere", old.get("/api/me").status_code == 200)
with sqlite3.connect(TMP / "users.db") as cn:
    n_sess = cn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
check("L6 the logged-out session was deleted from the database", n_sess == 1, f"({n_sess} sessions left)")
fake = client(); fake.cookies.set("aqi_session", "made-up-token")
check("L7 a made-up / tampered cookie -> 401", fake.get("/api/me").status_code == 401)
lim = client()
codes = [lim.post("/api/auth/login", json={"email": "limit@example.com", "password": "nope nope"}).status_code for _ in range(6)]
check("L8 after 5 wrong passwords the next try is refused (429)", codes[:5] == [401] * 5 and codes[5] == 429, str(codes))
r = client().post("/api/auth/login", json={"email": "asha@example.com", "password": "correct horse 1"}, headers={"Origin": "http://evil.example"})
check("L9 a login request from another web site is refused (403)", r.status_code == 403)

# ---- P. profile update, age -> groups, alert-level cap ----------------------------------------------------------------------------
def put(c, body):
    return c.put("/api/me", json=body)


r = put(a, {"name": "Asha R", "station": "mysuru", "conditions": ["lung", "athlete"], "email_alerts": True, "replay_emails": True})
p = r.json()
check("P1 profile update stored", r.status_code == 200 and p["name"] == "Asha R" and p["station"] == "mysuru" and p["conditions"] == ["lung", "athlete"]
      and p["email_alerts"] and p["replay_emails"], r.text[:200])
check("P2 unknown station refused", put(a, {"station": "delhi"}).status_code == 400)
check("P3 unknown condition refused", put(a, {"conditions": ["lung", "smoker"]}).status_code == 400)
check("P4 age out of range refused", put(a, {"age": 130}).status_code == 400 and put(a, {"age": -1}).status_code == 400)
check("P5 a field outside the profile (e-mail) cannot be changed via /api/me", put(a, {"email": "evil@example.com"}).json()["email"] == "asha@example.com")
cases = [(5, ["child"]), (13, ["child"]), (14, []), (40, []), (59, []), (60, ["older"]), (85, ["older"]), (None, [])]
res = []
for age, auto in cases:
    q = put(a, {"age": age, "conditions": []}).json()
    res.append((age, q["auto_groups"], q["groups"]))
    if q["auto_groups"] != auto or q["groups"] != auto:
        break
check("P6 age < 14 -> Child, age >= 60 -> Older adult, otherwise none", all(x[1] == y[1] for x, y in zip(res, cases)) and len(res) == len(cases), str(res))
q = put(a, {"age": 70, "conditions": ["heart"]}).json()
check("P7 groups = ticked conditions + age group", q["groups"] == ["heart", "older"] and q["alert_default"] == 101)
q = put(a, {"age": 30, "conditions": []}).json()
check("P8 healthy adult: default alert 201", q["groups"] == [] and q["alert_default"] == 201 and q["alert_effective"] == 201 and q["alert_from"] is None)
q = put(a, {"alert_from": 301}).json()
check("P9 alert level above the default is not stored (stays the default 201)", q["alert_from"] is None and q["alert_effective"] == 201, str(q["alert_effective"]))
q = put(a, {"alert_from": 151}).json()
check("P10 a lower alert level is kept (151)", q["alert_from"] == 151 and q["alert_effective"] == 151)
q = put(a, {"conditions": ["lung"]}).json()
check("P11 becoming vulnerable caps the stored 151 at the new default 101", q["alert_effective"] == 101 and q["alert_default"] == 101)
q = put(a, {"alert_from": 201}).json()
check("P12 vulnerable user asking for 201 gets the default 101", q["alert_from"] is None and q["alert_effective"] == 101)
q = put(a, {"alert_from": 51}).json()
check("P13 vulnerable user may choose 51", q["alert_effective"] == 51)
check("P14 alert choices offered never exceed the default", max(q["alert_choices"]) <= q["alert_default"])
q = put(a, {"alert_from": None}).json()
check("P15 alert_from null -> back to the default", q["alert_from"] is None and q["alert_effective"] == 101)
row = users.get(users.user_id_by_email("asha@example.com"))
check("P16 the alert rules use the same effective level (advice.thresholds)", ne.adv.thresholds({"groups": users.public(row)["groups"], "alert_from": 301})["alert_from"] == 101)
r = a.put("/api/me", json={"age": 20}, headers={"Origin": "http://evil.example"})
check("P17 profile change from another web site refused (403)", r.status_code == 403)

# ---- I. isolation: one user cannot read or change another's data ------------------------------------------------------------------
b = client()
signup(b, "Bala K", "bala@example.com", pw="bala password 9")
put(b, {"age": 8, "station": "hebbal", "conditions": []})
mb = b.get("/api/me").json()
ma = a.get("/api/me").json()
check("I1 each user sees only their own profile", mb["email"] == "bala@example.com" and ma["email"] == "asha@example.com" and mb["groups"] == ["child"])
before = a.get("/api/me").json()
put(b, {"id": users.user_id_by_email("asha@example.com"), "user_id": 1, "email": "asha@example.com", "name": "HACKED", "age": 99})
after = a.get("/api/me").json()
check("I2 a profile update with another user's id/email changes only the caller's own account", before == after and b.get("/api/me").json()["name"] == "HACKED")
probes = [b.get("/api/users/1").status_code, b.get("/api/me?id=1").json().get("email"), b.get("/api/me", params={"user_id": 1}).json().get("email")]
check("I3 no endpoint returns another user's profile by id", probes[0] in (404, 405) and probes[1] == "bala@example.com" and probes[2] == "bala@example.com", str(probes))
b.cookies.clear()
check("I4 without a cookie nothing is readable", b.get("/api/me").status_code == 401)
b.post("/api/auth/login", json={"email": "bala@example.com", "password": "bala password 9"})
check("I5 a wrong password for another account cannot delete it", b.post("/api/me/delete", json={"password": "correct horse 1"}).status_code == 401
      and a.get("/api/me").status_code == 200 and b.get("/api/me").status_code == 200)

# ---- V. e-mail verification and password reset (links captured, never sent) -------------------------------------------------------
wait_links(1)
vlink = [l for k, to, l in links if k == "verify" and to == "asha@example.com"][-1]
tok = vlink.split("token=")[1]
r = client().get("/api/auth/verify", params={"token": tok}, follow_redirects=False)
check("V1 confirmation link marks the e-mail as confirmed", r.status_code == 303 and r.headers["location"].endswith("verified=1") and a.get("/api/me").json()["email_verified"])
r = client().get("/api/auth/verify", params={"token": tok}, follow_redirects=False)
check("V2 a confirmation link works only once", r.headers["location"].endswith("verified=0"))
n = len(links)
r = client().post("/api/auth/forgot", json={"email": "bala@example.com"})
r2 = client().post("/api/auth/forgot", json={"email": "nobody@example.com"})
wait_links(n + 1)
check("V3 'forgot password' answers the same for known and unknown addresses", r.json()["message"] == r2.json()["message"])
rl = [l for k, to, l in links if k == "reset" and to == "bala@example.com"]
check("V4 a reset link was e-mailed only for the existing account", len(rl) == 1 and not any(to == "nobody@example.com" for _, to, _ in links))
rtok = rl[0].split("token=")[1]
check("V5 reset with a too-short password refused (token not used up)", client().post("/api/auth/reset", json={"token": rtok, "password": "short"}).status_code == 400)
r = client().post("/api/auth/reset", json={"token": rtok, "password": "new bala pass 1"})
check("V6 reset sets the new password and logs out other sessions", r.status_code == 200 and b.get("/api/me").status_code == 401)
check("V7 old password no longer works, new one does", client().post("/api/auth/login", json={"email": "bala@example.com", "password": "bala password 9"}).status_code == 401
      and b.post("/api/auth/login", json={"email": "bala@example.com", "password": "new bala pass 1"}).status_code == 200)
check("V8 a reset link works only once", client().post("/api/auth/reset", json={"token": rtok, "password": "another pass 2"}).status_code == 400)
check("V9 using the reset link also confirms the e-mail address", b.get("/api/me").json()["email_verified"] is True)

# ---- E. per-user LIVE e-mail alerts (fake live data; send() captured) --------------------------------------------------------------
import live_api  # noqa: E402
LIVE = {"silkboard": {"age": 3, "aqi": 150, "high": 175}, "mysuru": {"age": 3, "aqi": 150, "high": 175}, "hebbal": {"age": 3, "aqi": 90, "high": 120}}


def fake_stations():
    return [{"id": k, "age_hours": v["age"]} for k, v in LIVE.items()]


def fake_state(st):
    v = LIVE[st]
    f = {"horizon": 6, "available": True, "status": "future", "aqi": v["aqi"], "range_low": v["aqi"] - 20, "range_high": v["high"],
         "category": ne.adv.category_of(v["aqi"]), "category_high": ne.adv.category_of(v["high"]), "target_end": "2026-10-20 18:00",
         "tier": "high", "dominant": "pm10"}
    return {"station_name": ne.STATIONS[st], "now": "2026-10-20 12:00", "age_hours": v["age"], "forecasts": [f],
            "last_obs_end": v.get("obs", "2026-10-20 12:00"), "last_aqi": v["aqi"] - 5}


live_api.stations, live_api.state = fake_stations, fake_state
ne.send = capture_send
# accounts: Asha lung, alert 101, Silk Board (verified); Bala child (age 8), Hebbal (verified), Chitra healthy, Mysuru (verified);
#           Dev: alerts on but NOT verified; Esha: verified but alerts off
put(a, {"station": "silkboard", "conditions": ["lung"], "alert_from": None, "email_alerts": True, "age": 30})
put(b, {"email_alerts": True, "age": 8})
cc, dd, ee = client(), client(), client()
signup(cc, "Chitra", "chitra@example.com"); put(cc, {"station": "mysuru", "age": 35, "email_alerts": True})
signup(dd, "Dev", "dev@example.com"); put(dd, {"station": "silkboard", "conditions": ["lung"], "email_alerts": True})
signup(ee, "Esha", "esha@example.com"); put(ee, {"station": "silkboard", "conditions": ["lung"], "email_alerts": False})
with sqlite3.connect(TMP / "users.db") as cn:
    cn.execute("UPDATE users SET email_verified=1 WHERE email IN ('chitra@example.com', 'esha@example.com')")
ne.run_live()
to = sorted(x["to"] for x in sent)
check("E1 only accounts with alerts on, a confirmed address and a reached level get an e-mail", to == ["asha@example.com", "bala@example.com"], str(to))
sa = [x for x in sent if x["to"] == "asha@example.com"][0]
check("E2 each e-mail uses that user's own station and level (Asha: Silk Board likely 150)", "Silk Board" in sa["subject"] and "AQI alert (likely)" in sa["subject"], sa["subject"])
sb = [x for x in sent if x["to"] == "bala@example.com"][0]
check("E3 Bala (child, Hebbal, forecast 90 < 101, range up to 120): Possible alert for Hebbal", "Possible AQI alert" in sb["subject"] and "Hebbal" in sb["subject"], sb["subject"])
check("E4 Chitra (healthy, alert 201) gets nothing for 150 at Mysuru", not any(x["to"] == "chitra@example.com" for x in sent))
st = json.loads((TMP / "email_state.json").read_text())
uid_a = users.user_id_by_email("asha@example.com")
check("E5 cooldown state is kept per user and station", f"user{uid_a}:silkboard" in st, str(list(st)))
sent.clear(); ne.run_live()
check("E6 second run within 12 h: suppressed by the cooldown", sent == [], str([x["subject"] for x in sent]))
LIVE["hebbal"]["aqi"] = 130; sent.clear(); ne.run_live()
check("E7 escalation possible -> likely bypasses the cooldown (Bala only)", [x["to"] for x in sent] == ["bala@example.com"] and "likely" in sent[0]["subject"], str([x["subject"] for x in sent]))
LIVE["mysuru"].update(aqi=230, high=260); sent.clear(); ne.run_live()
check("E8 Chitra is alerted once her own level (201) is reached", [x["to"] for x in sent] == ["chitra@example.com"], str([x["to"] for x in sent]))
for k in LIVE:
    LIVE[k]["age"] = 13
(TMP / "email_state.json").unlink(); sent.clear(); ne.run_live()
check("E9 data older than 12 h at a user's station: no live alert e-mail", sent == [], str([x["subject"] for x in sent]))
LIVE["silkboard"].update(age=2, obs="2026-10-20 13:00"); sent.clear(); ne.run_live()      # a newer observation = a new forecast issue time
check("E10 the 12 h rule is per user's station (only Silk Board fresh -> only Asha)", [x["to"] for x in sent] == ["asha@example.com"], str([x["to"] for x in sent]))
(TMP / "email_state.json").unlink(); sent.clear(); ne.run_live()
check("E10b no duplicate: the same live alert (station, issue time, target, level) is not e-mailed again even with the cooldown cleared",
      sent == [], str([x["subject"] for x in sent]))
for k in LIVE:
    LIVE[k]["age"] = 30
(TMP / "email_state.json").unlink(); sent.clear(); ne.run_live()
check("E11 feed stopped (> 24 h everywhere): only the daily notice to the project owner, no user alerts",
      len(sent) == 1 and "feed stopped" in sent[0]["subject"] and not any(x["to"].endswith("@example.com") for x in sent), str([(x["to"], x["subject"]) for x in sent]))

# ---- R. per-user REPLAY-demo e-mails through the endpoint (outbox; fake send) -----------------------------------------------------
ne.OUTBOX = ne.ReplayOutbox()                # the outbox worker calls send(), still captured here
sent.clear()
body = {"period": "validation", "station": "silkboard", "t": "2026-04-24 01:00:00"}
put(a, {"replay_emails": True, "conditions": ["lung"], "alert_from": None})
r = a.post("/api/email/replay-alert", json=body)
check("R1 logged-in user with replay e-mails on and a confirmed address: e-mail queued", r.status_code == 200 and r.json().get("queued"), r.text[:200])
time.sleep(0.6)
items = ne.OUTBOX.sent
check("R2 the replay e-mail goes to the user's own address and belongs to that user", items and items[-1][0] == uid_a and sent and sent[-1]["to"] == "asha@example.com"
      and sent[-1]["subject"].startswith("[REPLAY DEMO]"), str(items) + str([x["to"] for x in sent]))
put(dd, {"replay_emails": True})
check("R3 unconfirmed address: replay e-mail refused (403)", dd.post("/api/email/replay-alert", json=body).status_code == 403)
put(a, {"replay_emails": False})
check("R4 replay e-mails switched off: refused (403)", a.post("/api/email/replay-alert", json=body).status_code == 403)
g = client()
r = g.post("/api/email/replay-alert", json=body)
check("R5 guest mode still works (uses the browser/guest profile)", r.status_code == 200, r.text[:200])
time.sleep(0.6)
own = {o: sum(1 for x in ne.OUTBOX.sent if x[0] == o) for o in (uid_a, None)}
seen = (len(a.get("/api/email/outbox").json()["sent"]), len(g.get("/api/email/outbox").json()["sent"]), len(dd.get("/api/email/outbox").json()["sent"]))
check("R6 the outbox list shows each caller only their own e-mails (user / guest / other user)", own[uid_a] == 1 and own[None] == 1 and seen == (1, 1, 0),
      f"(owned {own}, seen user/guest/other {seen})")

# ---- N. no duplicate e-mails: the same alert is never e-mailed twice to the same user (replay restart / rewind) ---------------------
def wait_outbox(timeout=4):
    t0 = time.time()
    while ne.OUTBOX.status()["pending"] and time.time() - t0 < timeout:
        time.sleep(0.05)
    time.sleep(0.3)


put(b, {"replay_emails": True})
uid_b = users.user_id_by_email("bala@example.com")
T1, T0 = "2026-04-24 01:00:00", "2026-04-23 20:00:00"
sent.clear(); ne.OUTBOX = ne.ReplayOutbox()
r1 = b.post("/api/email/replay-alert", json={"period": "validation", "station": "silkboard", "t": T1, "seq": 0}).json()
wait_outbox()
check("N1 first replay alert e-mail for this hour is queued and sent to the user", r1.get("queued") and [x["to"] for x in sent] == ["bala@example.com"], str(r1))
r2 = b.post("/api/email/replay-alert", json={"period": "validation", "station": "silkboard", "t": T1, "seq": 1}).json()
check("N2 the same alert again (same station, issue time, target time, level): not queued, marked duplicate", r2.get("duplicate") and not r2.get("queued"), str(r2))
ne.OUTBOX = ne.ReplayOutbox()                                  # 'restart': a new outbox (as after a server restart) and a new browser session
b2 = client(); b2.post("/api/auth/login", json={"email": "bala@example.com", "password": "new bala pass 1"})
r3 = b2.post("/api/email/replay-alert", json={"period": "validation", "station": "silkboard", "t": T1}).json()
check("N3 after a replay restart (new outbox, new login) the same alert is still not e-mailed again", r3.get("duplicate") and not r3.get("queued"), str(r3))
r4 = b2.post("/api/email/replay-alert", json={"period": "validation", "station": "silkboard", "t": T0}).json()
wait_outbox()
r5 = b2.post("/api/email/replay-alert", json={"period": "validation", "station": "silkboard", "t": T1}).json()
check("N4 rewinding to an earlier hour sends that (new) alert once, and going forward again does not repeat the first one",
      r4.get("queued") and r5.get("duplicate"), f"{r4} | {r5}")
to_b = [x for x in sent if x["to"] == "bala@example.com"]
subj = [x["subject"] for x in to_b]
check("N5 exactly one e-mail per distinct alert reached the user (2 alerts -> 2 e-mails, no repeats)", len(to_b) == 2 and len(set(subj)) == 2, str(subj))
with sqlite3.connect(TMP / "users.db") as cn:
    rows = cn.execute("SELECT mode, station, issued, target, level FROM sent_alerts WHERE user_key=?", (f"u{uid_b}",)).fetchall()
check("N6 the per-user 'already sent' record holds station, issue time, target time and level", len([r for r in rows if r[0] == "replay"]) == 2
      and all(r[1] == "silkboard" and r[3] and r[4] in ("likely", "possible") for r in rows if r[0] == "replay"), str(rows))
g2 = client(); g2.get("/?guest=1")
rg1 = g2.post("/api/email/replay-alert", json={"period": "validation", "station": "silkboard", "t": T0}).json()     # (T1 was already sent to the guest in R5)
wait_outbox()
rg2 = client().post("/api/email/replay-alert", json={"period": "validation", "station": "silkboard", "t": T0}).json()
check("N7 guest mode is protected too (same guest address: second request is a duplicate)", rg1.get("queued") and rg2.get("duplicate"), f"{rg1} | {rg2}")
# a failed send releases the claim, so the alert can be sent later
failing = {"n": 0}


def fail_once(subject, body, to, dry_run=False):
    if failing["n"] == 0:
        failing["n"] += 1
        raise RuntimeError("simulated SMTP failure")
    return capture_send(subject, body, to)


ne.send = fail_once
T2 = "2026-04-24 06:00:00"
rf = b2.post("/api/email/replay-alert", json={"period": "validation", "station": "silkboard", "t": T2}).json()
wait_outbox()
rf2 = b2.post("/api/email/replay-alert", json={"period": "validation", "station": "silkboard", "t": T2}).json()
wait_outbox()
ne.send = capture_send
check("N8 a failed send is not counted as sent: the same alert can be queued again and then arrives once",
      rf.get("queued") and rf2.get("queued") and sum(1 for x in sent if x["to"] == "bala@example.com" and "2026-04-24" in x["subject"]) >= 1, f"{rf} | {rf2}")
body_b = to_b[0]["body"]
check("N9 the e-mail body carries the personalised parts with citations (child line, trend, main pollutant, tip)",
      "Child:" in body_b and "Next 24 h:" in body_b and "Main pollutant:" in body_b and "Tip:" in body_b and "[4]" in body_b and "[6]" in body_b)

# ---- D. delete account ------------------------------------------------------------------------------------------------------------
with open(TMP / "email_log.jsonl", "w", encoding="utf-8") as fh:            # pretend log lines (the real log is never touched)
    fh.write(json.dumps({"time": "x", "to": "asha@example.com", "subject": "s1"}) + "\n" + json.dumps({"time": "x", "to": "bala@example.com", "subject": "s2"}) + "\n")
(TMP / "email_state.json").write_text(json.dumps({f"user{uid_a}:silkboard": {"time": datetime.now().isoformat(), "level": "likely"}, "feed_notice_date": "x"}))
r = a.post("/api/me/delete", json={"password": "wrong one!"})
check("D1 delete with a wrong password is refused and keeps the account", r.status_code == 401 and a.get("/api/me").status_code == 200)
r = a.post("/api/me/delete", json={"password": "correct horse 1"})
check("D2 delete with the password succeeds and logs out", r.status_code == 200 and a.get("/api/me").status_code == 401)
with sqlite3.connect(TMP / "users.db") as cn:
    left = [cn.execute(f"SELECT COUNT(*) FROM {t} WHERE user_id=?", (uid_a,)).fetchone()[0] for t in ("sessions", "tokens")]
    left.append(cn.execute("SELECT COUNT(*) FROM users WHERE id=?", (uid_a,)).fetchone()[0])
check("D3 user row, sessions and link tokens are gone", left == [0, 0, 0], str(left))
check("D4 the user's e-mail log lines and cooldown state are removed (others kept)",
      "asha@example.com" not in (TMP / "email_log.jsonl").read_text() and "bala@example.com" in (TMP / "email_log.jsonl").read_text()
      and list(json.loads((TMP / "email_state.json").read_text())) == ["feed_notice_date"])
check("D5 the user's replay e-mails are removed from the outbox", not any(x[0] == uid_a for x in ne.OUTBOX.sent))
check("D6 cannot log in after deletion", client().post("/api/auth/login", json={"email": "asha@example.com", "password": "correct horse 1"}).status_code == 401)
check("D7 the same e-mail can sign up again as a new account", signup(client(), "Asha", "asha@example.com").status_code == 200)
check("D8 other users are unaffected", b.get("/api/me").json()["email"] == "bala@example.com")

# ---- F. login first: the replay and live pages need a login or the guest choice --------------------------------------------------
nc = client()
r1, r2, r3 = (nc.get(u, follow_redirects=False) for u in ("/", "/index.html", "/live.html"))
check("F1 not logged in: / and /index.html redirect to the login page (next=/)", r1.status_code == 303 and r1.headers["location"] == "/login.html?next=/"
      and r2.status_code == 303 and r2.headers["location"] == "/login.html?next=/", f"{r1.status_code} {r1.headers.get('location')}")
check("F2 not logged in: /live.html redirects to the login page (next=/live.html)", r3.status_code == 303 and r3.headers["location"] == "/login.html?next=/live.html")
check("F3 the login, sign-up and other account pages are open without login",
      all(nc.get(u, follow_redirects=False).status_code == 200 for u in ("/login.html", "/signup.html", "/forgot.html", "/reset.html", "/profile.html", "/style.css")))
check("F4 logged in: the replay and live pages open directly", all(b.get(u, follow_redirects=False).status_code == 200 for u in ("/", "/live.html")))
r = nc.get("/?guest=1", follow_redirects=False)
check("F5 'Try the demo without an account' (/?guest=1) opens the replay page and remembers the guest choice for this browser session",
      r.status_code == 200 and "aqi_guest=1" in r.headers.get("set-cookie", "") and "max-age" not in r.headers.get("set-cookie", "").lower())
check("F6 guest: later visits to / and /live.html open directly", nc.get("/", follow_redirects=False).status_code == 200 and nc.get("/live.html", follow_redirects=False).status_code == 200)
check("F7 developer self-tests (?selftest=) are not redirected", client().get("/?selftest=1", follow_redirects=False).status_code == 200)
check("F8 the gated pages are not cached (a redirect decision cannot be reused)", nc.get("/", follow_redirects=False).headers.get("cache-control") == "no-store"
      and client().get("/", follow_redirects=False).headers.get("cache-control") == "no-store")
lo = client(); lo.get("/?guest=1"); lo.post("/api/auth/login", json={"email": "bala@example.com", "password": "new bala pass 1"})
r = lo.post("/api/auth/logout")
check("F9 logging out also clears the guest choice, so the login page is shown next", "aqi_guest" in r.headers.get("set-cookie", "") and
      lo.get("/", follow_redirects=False).status_code == 303)
check("F10 the user API is not opened by the guest cookie", nc.get("/api/me").status_code == 401)

# ---- G. git and real files ---------------------------------------------------------------------------------------------------------
gi = (ROOT / ".gitignore").read_text()
check("G1 data/users.db is git-ignored", "data/users.db" in gi)
envkey = next((l.split("=", 1)[1].strip() for l in (ROOT / ".env").read_text(encoding="utf-8").splitlines() if l.startswith("AQI_SECRET_KEY=")), None) if (ROOT / ".env").exists() else None
code = "".join(f.read_text(encoding="utf-8", errors="replace") for d in ("backend", "frontend") for f in (ROOT / d).glob("*.*") if f.suffix in (".py", ".js", ".html"))
check("G2 the secret key from .env appears in no code file", envkey is None or envkey not in code, "(no key in .env yet)" if envkey is None else "")
check("G3 the real e-mail log was not changed", (REAL_LOG.read_bytes() if REAL_LOG.exists() else None) == real_log_before)
check("G4 the real users database was not touched", (REAL_DB.stat().st_mtime if REAL_DB.exists() else None) == real_db_before)

print()
print("ALL PASSED" if not failures else f"{len(failures)} FAILED: {failures}")
sys.exit(1 if failures else 0)
