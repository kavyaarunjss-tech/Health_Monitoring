"""Tests for the WhatsApp (Twilio) alert channel. NEVER sends real messages:
  * AQI_EMAIL_FAKE=1 -> notify_twilio uses its in-memory FakeClient; in addition the real twilio.rest.Client and smtplib are replaced by
    classes that raise, so any attempt to reach Twilio or Gmail fails the test;
  * the API runs in-process (FastAPI TestClient, no network port); the profile-page check at the end uses its own server on port 8039
    (DevTools 9339), never port 8000.
Covers: phone validation, message length, channel selection, rate limit (and independence from the e-mail limit), cooldown shared with
e-mail, de-duplication, failure isolation (either channel failing), error codes 63015 / 63016 shown on the profile, the test button, replay
alerts through the shared queue, delete account, and that no Twilio token appears in logs, output or API responses.

usage (project root, aqi env):  python backend\\test_twilio.py
"""
import contextlib
import io
import json
import os
import smtplib
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TMP = Path(tempfile.mkdtemp(prefix="aqi_twilio_"))
FAKE_TOKEN = "FAKE-TWILIO-TOKEN-must-never-appear-9f3c"
os.environ.update(AQI_EMAIL_FAKE="1", AQI_USERS_DB=str(TMP / "users.db"), AQI_SECRET_KEY="twilio-test-" + "w" * 40,
                  AQI_EMAIL_STATE_FILE=str(TMP / "email_state.json"), AQI_EMAIL_LOG_FILE=str(TMP / "email_log.jsonl"),
                  AQI_RATE_FILE=str(TMP / "rate.json"), AQI_PROFILE_FILE=str(TMP / "profile.json"), AQI_MAIL_MIN_GAP_S="0", AQI_MAIL_PER_HOUR="1000",
                  AQI_WHATSAPP_LOG_FILE=str(TMP / "whatsapp_log.jsonl"), AQI_WA_RATE_FILE=str(TMP / "wa_rate.json"), AQI_WA_MIN_GAP_S="0",
                  AQI_WA_PER_HOUR="1000", AQI_WA_CHECK_S="0.05",
                  TWILIO_ACCOUNT_SID="ACfake0000000000000000000000000000", TWILIO_AUTH_TOKEN=FAKE_TOKEN, TWILIO_WHATSAPP_FROM="whatsapp:+17372508034")
sys.path.insert(0, str(ROOT / "backend"))
REAL_TOKEN = next((l.split("=", 1)[1].strip().strip('"') for l in (ROOT / ".env").read_text(encoding="utf-8").splitlines()
                   if l.startswith("TWILIO_AUTH_TOKEN=")), "") if (ROOT / ".env").exists() else ""
REAL_DB = ROOT / "data" / "users.db"
real_db_before = REAL_DB.stat().st_mtime if REAL_DB.exists() else None


class NoNetwork:
    def __init__(self, *a, **k):
        raise AssertionError("a real Twilio / SMTP client was created in a test")


import twilio.rest  # noqa: E402
twilio.rest.Client = NoNetwork
smtplib.SMTP_SSL = smtplib.SMTP = NoNetwork

from fastapi.testclient import TestClient  # noqa: E402
import app as appmod  # noqa: E402
import live_api  # noqa: E402
import notify_email as ne  # noqa: E402
import notify_twilio as ntw  # noqa: E402
import users  # noqa: E402

failures, OUT, RESPONSES = [], io.StringIO(), []


def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  {extra}" if extra else ""))
    if not cond:
        failures.append(name)


emails, FAIL_EMAIL = [], set()


def fake_send(subject, body, to, dry_run=False):
    if to in FAIL_EMAIL:
        raise ConnectionError("simulated SMTP failure")
    emails.append({"to": to, "subject": subject, "body": body})
    return True


ne.send = fake_send
FC = ntw.FAKE_CLIENT
wa_to = lambda: [m["to"].replace("whatsapp:", "") for m in FC.sent]          # noqa: E731


def client():
    return TestClient(appmod.app)


def account(name, email, profile, verified=True):
    c = client()
    r = c.post("/api/auth/signup", json={"name": name, "email": email, "password": "test password 1", "consent": True})
    RESPONSES.append(r.text)
    r = c.put("/api/me", json=profile)
    RESPONSES.append(r.text)
    assert r.status_code == 200, r.text
    if verified:
        with sqlite3.connect(TMP / "users.db") as cn:
            cn.execute("UPDATE users SET email_verified=1 WHERE email=?", (email,))
    return c, users.user_id_by_email(email)


def wait_bg(seconds=0.4):
    ntw.wait_checks(5)
    time.sleep(seconds)


# ---- Z. safety ---------------------------------------------------------------------------------------------------------------------
check("Z1 fake mode is on (AQI_EMAIL_FAKE=1)", ntw.FAKE is True and ne.FAKE is True)
r = ntw.send_whatsapp("+919800000001", "hello", check_delivery=False)
check("Z2 sending uses the in-memory fake client; the real twilio Client (replaced by a raising class) is never created",
      r["ok"] and FC.sent and FC.sent[-1]["to"] == "whatsapp:+919800000001")
check("Z3 credentials come from the environment (test token), not from the real .env", ntw.env()["TWILIO_AUTH_TOKEN"] == FAKE_TOKEN)
FC.reset()

# ---- V. phone validation -----------------------------------------------------------------------------------------------------------
ok_cases = {"+919876543210": "+919876543210", "+91 98765 43210": "+919876543210", "+1 (737) 250-8034": "+17372508034", "": None}
bad_cases = ["9876543210", "+0123456789", "+91abc43210", "+1234567", "+1234567890123456", "00919876543210"]
res_ok = {k: users.clean_whatsapp(k) for k in ok_cases}
res_bad = []
for b in bad_cases:
    try:
        users.clean_whatsapp(b)
        res_bad.append(b)
    except users.AuthError:
        pass
check("V1 E.164 numbers are accepted and normalised (spaces, dashes, brackets removed); empty = no number", res_ok == ok_cases, str(res_ok))
check("V2 invalid numbers are refused (no +, leading 0, letters, too short, too long, 00 prefix)", not res_bad, str(res_bad))
cv, _ = account("Val", "val@example.com", {"station": "silkboard"})
r1 = cv.put("/api/me", json={"whatsapp": "98765 43210"}); r2 = cv.put("/api/me", json={"whatsapp_alerts": True})
r3 = cv.put("/api/me", json={"whatsapp": "+91 98765 43210", "whatsapp_alerts": True})
RESPONSES.extend([r1.text, r2.text, r3.text])
check("V3 profile API: invalid number -> 400; WhatsApp alerts without a number -> 400; valid number stored in E.164",
      r1.status_code == 400 and r2.status_code == 400 and r3.status_code == 200 and r3.json()["whatsapp"] == "+919876543210", f"{r1.status_code} {r2.status_code} {r3.text[:120]}")
r = ntw.send_whatsapp("12345", "x", check_delivery=False)
check("V4 send_whatsapp refuses an invalid number without contacting Twilio", not r["ok"] and r["status"] == "invalid" and not FC.sent)

# ---- L. message text ---------------------------------------------------------------------------------------------------------------
import advice as adv  # noqa: E402
lens, bad = [], []
long_advice = "Lung disease: " + "avoid outdoor physical activities and keep your prescribed medicines readily available " * 12 + "[4]"
for aqi, level, mode, esc, line in [(150, "likely", "live", "", "Lung disease: keep your prescribed medicines readily available [4]"),
                                     (90, "possible", "replay", "", "Child: reduce prolonged or strenuous outdoor physical exertion [4]"),
                                     (256, "likely", "replay", "category", long_advice), (420, "likely", "live", "level", long_advice)]:
    f = {"aqi": aqi, "category": adv.category_of(aqi), "target_end": "2026-04-24 08:00", "horizon": 6, "range_high": aqi + 40,
         "category_high": adv.category_of(aqi + 40)}
    t = ntw.compose(mode, "Kalyana Nagara, Chikkamagaluru", level, f, line, "2026-04-24 02:00")
    lens.append(len(t))
    must = ["Kalyana Nagara, Chikkamagaluru", f"AQI {aqi}", f["category"], "2026-04-24 08:00", "Likely" if level == "likely" else "Possible"]
    if len(t) >= 600 or "http" in t or "www." in t or "<" in t or not all(m in t for m in must) or not t.split("\n")[2].startswith(line[:20]):
        bad.append(t[:80])
check("L1 WhatsApp text: under 600 characters (even with a very long advice line), plain text, no links; has station, AQI, category, "
      "time, Likely/Possible and one advice line", not bad and max(lens) < 600, f"lengths {lens}; bad {bad}")
check("L2 replay messages say [REPLAY DEMO]; escalations say UPDATE", "[REPLAY DEMO]" in ntw.compose("replay", "S", "likely", f, "x", "t")
      and "UPDATE, higher category" in ntw.compose("live", "S", "likely", f, "x", "t", "category"))

# ---- R. rate limit (same rule as e-mail: 1 per 60 s, 10 per hour), independent of the e-mail limit -----------------------------------
ntw.MIN_GAP_S, ntw.PER_HOUR, ntw.RATE_FILE = 60, 10, TMP / "wa_rate_unit.json"
seq = []
for t_ in (1000, 1030, 1061, 1200, 1300, 1400, 1500, 1600, 1700, 1800, 1900, 2000, 4700):
    try:
        ntw.reserve_slot(now=t_); seq.append("ok")
    except ntw.RateLimited:
        seq.append("wait")
check("R1 one WhatsApp per 60 s and at most 10 per hour (real time); allowed again after the hour", seq ==
      ["ok", "wait", "ok", "ok", "ok", "ok", "ok", "ok", "ok", "ok", "ok", "wait", "ok"], str(seq))
ne.MIN_GAP_S, ne.RATE_FILE = 60, TMP / "rate_unit.json"
ne.reserve_replay_slot(now=5000)
try:
    ntw.reserve_slot(now=5001); indep = True
except ntw.RateLimited:
    indep = False
check("R2 the WhatsApp limit is separate from the e-mail limit (an e-mail just sent does not block a WhatsApp)", indep)
ne.MIN_GAP_S, ne.RATE_FILE = 0, TMP / "rate.json"
ntw.MIN_GAP_S, ntw.PER_HOUR, ntw.RATE_FILE = 0, 1000, TMP / "wa_rate.json"

# ---- C. channel selection (live alerts) ----------------------------------------------------------------------------------------------
LIVE = {"silkboard": {"age": 3, "aqi": 150, "high": 175, "obs": "2026-10-24 10:00"}, "hebbal": {"age": 3, "aqi": 90, "high": 120, "obs": "2026-10-24 10:00"}}


def fake_stations():
    return [{"id": k, "age_hours": v["age"]} for k, v in LIVE.items()]


def fake_state(st):
    v = LIVE[st]
    f = {"horizon": 6, "available": True, "status": "future", "aqi": v["aqi"], "range_low": v["aqi"] - 20, "range_high": v["high"],
         "category": adv.category_of(v["aqi"]), "category_high": adv.category_of(v["high"]), "target_end": "2026-10-24 16:00", "tier": "high",
         "dominant": "pm10"}
    return {"station_name": ne.STATIONS[st], "now": "2026-10-24 12:00", "age_hours": v["age"], "forecasts": [f],
            "last_obs_end": v["obs"], "last_aqi": v["aqi"] - 5}


live_api.stations, live_api.state = fake_stations, fake_state
lung = {"station": "silkboard", "conditions": ["lung"], "age": 40}
ca, ia = account("A mail", "a@example.com", {**lung, "email_alerts": True})
cb, ib = account("B wa", "b@example.com", {**lung, "whatsapp": "+911111111111", "whatsapp_alerts": True})
cc, ic = account("C both", "c@example.com", {**lung, "email_alerts": True, "whatsapp": "+912222222222", "whatsapp_alerts": True})
cd, id_ = account("D unconfirmed", "d@example.com", {**lung, "email_alerts": True, "whatsapp": "+913333333333", "whatsapp_alerts": True}, verified=False)
ce, ie = account("E none", "e@example.com", {**lung, "whatsapp": "+914444444444"})
cv.put("/api/me", json={"whatsapp_alerts": False})
FC.reset(); emails.clear()
with contextlib.redirect_stdout(OUT):
    ne.run_live()
wait_bg()
check("C1 e-mail only -> e-mail; WhatsApp only -> WhatsApp; both -> both; unconfirmed e-mail + WhatsApp -> WhatsApp only; none -> nothing",
      sorted(m["to"] for m in emails) == ["a@example.com", "c@example.com"] and sorted(wa_to()) == ["+911111111111", "+912222222222", "+913333333333"],
      f"emails {sorted(m['to'] for m in emails)}, whatsapp {sorted(wa_to())}")
msg = FC.sent[0]["body"] if FC.sent else ""
check("C2 the live WhatsApp text is the short version (station, AQI, category, Likely) and under 600 characters",
      "Silk Board" in msg and "AQI 150" in msg and "Moderate" in msg and "Likely" in msg and len(msg) < 600 and "[REPLAY" not in msg, msg[:160])

# ---- K. cooldown shared with e-mail, escalation, de-duplication ----------------------------------------------------------------------------
FC.reset(); emails.clear()
with contextlib.redirect_stdout(OUT):
    ne.run_live()
wait_bg()
check("K1 second run within 12 h: no e-mail and no WhatsApp (one cooldown for both channels)", not emails and not FC.sent, f"{emails} {FC.sent}")
cf, i_f = account("F", "f@example.com", {"station": "hebbal", "conditions": ["lung"], "age": 40, "email_alerts": True})
FC.reset(); emails.clear()
with contextlib.redirect_stdout(OUT):
    ne.run_live()                                                                     # F: Possible alert at Hebbal, by e-mail only
cf.put("/api/me", json={"whatsapp": "+915555555555", "whatsapp_alerts": True})
with contextlib.redirect_stdout(OUT):
    ne.run_live()                                                                     # same alert again with WhatsApp now on
wait_bg()
check("K2 cooldown is shared: an alert already e-mailed starts the cooldown, so turning WhatsApp on does not resend it within 12 h",
      [m["to"] for m in emails] == ["f@example.com"] and "+915555555555" not in wa_to(), f"{[m['to'] for m in emails]} {wa_to()}")
LIVE["hebbal"]["aqi"] = 130; FC.reset(); emails.clear()
with contextlib.redirect_stdout(OUT):
    ne.run_live()                                                                     # possible -> likely = escalation
wait_bg()
check("K3 escalation (possible -> likely) bypasses the shared cooldown on both channels", [m["to"] for m in emails] == ["f@example.com"]
      and wa_to() == ["+915555555555"], f"{[m['to'] for m in emails]} {wa_to()}")
(TMP / "email_state.json").unlink(); FC.reset(); emails.clear()
with contextlib.redirect_stdout(OUT):
    ne.run_live()
wait_bg()
check("K4 de-duplication: with the cooldown cleared, the same alerts are not sent again on either channel (per-channel 'already sent')",
      not emails and not FC.sent, f"{[m['to'] for m in emails]} {wa_to()}")
with sqlite3.connect(TMP / "users.db") as cn:
    modes = {r[0] for r in cn.execute("SELECT mode FROM sent_alerts WHERE user_key=?", (f"u{ic}",))}
check("K5 the 'already sent' record has a separate entry per channel (live / live-whatsapp)", modes == {"live", "live-whatsapp"}, str(modes))

# ---- F. failure isolation -------------------------------------------------------------------------------------------------------------
LIVE["silkboard"]["obs"] = "2026-10-24 11:00"                                         # a new hour: new alerts
(TMP / "email_state.json").unlink(); FC.reset(); emails.clear()
cg, ig = account("G", "g@example.com", {**lung, "email_alerts": True, "whatsapp": "+916666666661", "whatsapp_alerts": True})
ch, ih = account("H", "h@example.com", {**lung, "email_alerts": True, "whatsapp": "+916666666662", "whatsapp_alerts": True})
ci, ii = account("I", "i@example.com", {**lung, "email_alerts": True, "whatsapp": "+916666666663", "whatsapp_alerts": True})
FC.fail_create["+916666666661"] = 63015                                               # G: Twilio rejects at once (not joined)
FAIL_EMAIL.add("h@example.com")                                                       # H: e-mail fails
FC.fail_later["+916666666663"] = 63016                                                # I: accepted, then undelivered (outside 24 h)
with contextlib.redirect_stdout(OUT):
    ne.run_live()
wait_bg(0.6)
FAIL_EMAIL.clear()
alert_mail = lambda: [m["to"] for m in emails if "AQI alert" in m["subject"]]          # noqa: E731  (sign-up confirmation e-mails excluded)
check("F1 WhatsApp rejected (63015) -> the e-mail is still sent", "g@example.com" in alert_mail())
check("F2 e-mail failed -> the WhatsApp message is still sent", "+916666666662" in wa_to() and "h@example.com" not in alert_mail(), f"wa {wa_to()} mail {alert_mail()}")
wl = {k: users.public(users.get(v))["wa_last"] for k, v in (("G", ig), ("I", ii), ("H", ih))}
check("F3 the Twilio error code is stored with a plain reason for the profile page (63015 not joined, 63016 outside 24 h)",
      wl["G"] and wl["G"]["ok"] is False and wl["G"]["code"] == 63015 and "join twilio-trial" in wl["G"]["reason"]
      and wl["I"] and wl["I"]["ok"] is False and wl["I"]["code"] == 63016 and "24-hour" in wl["I"]["reason"] and wl["H"]["ok"] is True, json.dumps(wl)[:300])
with sqlite3.connect(TMP / "users.db") as cn:
    g_wa = cn.execute("SELECT COUNT(*) FROM sent_alerts WHERE user_key=? AND mode='live-whatsapp'", (f"u{ig}",)).fetchone()[0]
    i_wa = cn.execute("SELECT COUNT(*) FROM sent_alerts WHERE user_key=? AND mode='live-whatsapp'", (f"u{ii}",)).fetchone()[0]
    h_mail = cn.execute("SELECT COUNT(*) FROM sent_alerts WHERE user_key=? AND mode='live'", (f"u{ih}",)).fetchone()[0]
check("F4 a failed channel releases its 'already sent' claim (so it can be retried), the successful one keeps it", (g_wa, i_wa, h_mail) == (0, 0, 0), f"{(g_wa, i_wa, h_mail)}")
logtxt = (TMP / "whatsapp_log.jsonl").read_text(encoding="utf-8")
check("F5 the WhatsApp log records the Twilio error codes (63015, 63016), with masked numbers and no message text",
      '"code": 63015' in logtxt and '"code": 63016' in logtxt and "+916666666661" not in logtxt and "Silk Board" not in logtxt)

# ---- Q. replay alerts through the same queue -------------------------------------------------------------------------------------------
ne.OUTBOX = ne.ReplayOutbox(); FC.reset(); emails.clear()
cc.put("/api/me", json={"replay_emails": True, "replay_whatsapp": True})
body = {"period": "validation", "station": "silkboard", "t": "2026-04-24 01:00:00"}
r = cc.post("/api/email/replay-alert", json=body); RESPONSES.append(r.text)
time.sleep(0.8); wait_bg()
check("Q1 a replay alert for a user with both channels is queued on both and both are sent",
      r.status_code == 200 and r.json().get("queued") and r.json().get("whatsapp", {}).get("queued") and [m["to"] for m in emails] == ["c@example.com"]
      and wa_to() == ["+912222222222"] and FC.sent[0]["body"].startswith("[REPLAY DEMO]"), r.text[:200])
r2 = cc.post("/api/email/replay-alert", json=body); RESPONSES.append(r2.text)
check("Q2 the same replay alert again: duplicate on both channels (restart / rewind safe)", r2.json().get("duplicate") and r2.json()["whatsapp"].get("duplicate"))
cb.put("/api/me", json={"replay_whatsapp": True})
FC.reset(); emails.clear()
ntw.MIN_GAP_S = 3600
r3 = cb.post("/api/email/replay-alert", json={**body, "t": "2026-04-24 04:00:00"}); RESPONSES.append(r3.text)
cc.put("/api/me", json={"replay_whatsapp": False})
r4 = cc.post("/api/email/replay-alert", json={**body, "t": "2026-04-24 05:00:00"}); RESPONSES.append(r4.text)
time.sleep(1.0)
check("Q3 a rate-limited WhatsApp message waits in the queue without blocking e-mails behind it", [m["to"] for m in emails] == ["c@example.com"]
      and not FC.sent and any("[WhatsApp]" in s for s in ne.OUTBOX.status()["pending"]), f"{emails} {ne.OUTBOX.status()['pending']}")
ntw.MIN_GAP_S = 0
time.sleep(6.5); wait_bg()
check("Q4 ... and is sent once the WhatsApp limit allows", wa_to() == ["+911111111111"], str(wa_to()))
check("Q5 WhatsApp-only user: replay alerts go by WhatsApp although replay e-mails are off", r3.status_code == 200 and r3.json().get("queued"), r3.text[:200])

# ---- T. "Send test WhatsApp" -------------------------------------------------------------------------------------------------------------
FC.reset()
t1 = cb.post("/api/me/test-whatsapp", json={}); RESPONSES.append(t1.text)
wait_bg()
me_b = cb.get("/api/me").json(); RESPONSES.append(json.dumps(me_b))
check("T1 the test button sends one message to the user's number; the final result appears on the profile", t1.status_code == 200 and t1.json()["sent"]
      and wa_to() == ["+911111111111"] and "Test message" in FC.sent[0]["body"] and me_b["wa_last"]["ok"] and me_b["wa_last"]["kind"] == "test", t1.text[:160])
ntw.MIN_GAP_S = 60
t2 = cb.post("/api/me/test-whatsapp", json={}); RESPONSES.append(t2.text)
ntw.MIN_GAP_S = 0
check("T2 a second test within 60 s is refused by the rate limit (429)", t2.status_code == 429, t2.text[:120])
t3 = ca.post("/api/me/test-whatsapp", json={}); t4 = ca.post("/api/me/test-whatsapp", json={"whatsapp": "12345"}); RESPONSES.extend([t3.text, t4.text])
check("T3 no number -> 400; invalid number -> 400", t3.status_code == 400 and t4.status_code == 400)
FC.fail_later["+917777777777"] = 63015
t5 = ca.post("/api/me/test-whatsapp", json={"whatsapp": "+91 77777 77777"}); RESPONSES.append(t5.text)
wait_bg()
w = ca.get("/api/me").json()["wa_last"]
check("T4 a test to a phone that has not joined the sandbox: accepted first, then the profile shows 'failed' with 63015 and the join hint",
      t5.json()["sent"] and w["ok"] is False and w["code"] == 63015 and "join twilio-trial" in w["reason"], json.dumps(w))

# ---- P. Content Templates (ContentSid) and readable errors ---------------------------------------------------------------------------
FC.reset()
r = ntw.send_whatsapp("+919800000002", "free text", check_delivery=False, fields={"station": "S"})
check("P1 no TWILIO_WA_CONTENT_SID: the message is free-form Body text (no ContentSid)", r["ok"] and FC.sent[-1]["body"] == "free text"
      and FC.sent[-1]["content_sid"] is None)
os.environ["TWILIO_WA_CONTENT_SID"] = "HX" + "a" * 32
fields = ntw.alert_fields("replay", "Silk Board, Bengaluru", "possible", {"aqi": 90, "category": "Satisfactory", "target_end": "2026-04-24 08:00",
                          "horizon": 6, "range_high": 120, "category_high": "Moderate"}, "Lung disease:\nkeep   medicines\treadily available [4]", "02:00")
r = ntw.send_whatsapp("+919800000002", "free text", check_delivery=False, fields=fields)
m = FC.sent[-1]
cv = json.loads(m["content_variables"] or "{}")
check("P2 TWILIO_WA_CONTENT_SID set (layout aqi5): sent as ContentSid + 5 ContentVariables, no Body",
      r["ok"] and m["content_sid"] == "HX" + "a" * 32 and m["body"] is None and sorted(cv) == ["1", "2", "3", "4", "5"], json.dumps(m)[:300])
check("P3 template variables: station, AQI + category, time, Likely/Possible, advice; single-line (no newlines/tabs/runs of spaces)",
      cv["1"] == "[REPLAY DEMO] Silk Board, Bengaluru" and "AQI 90 (Satisfactory)" in cv["2"] and "120 (Moderate)" in cv["2"] and "08:00" in cv["3"]
      and cv["4"] == "Possible" and cv["5"] == "Lung disease: keep medicines readily available [4]"
      and not any(ch in "".join(cv.values()) for ch in "\n\t") and "  " not in "".join(cv.values()), json.dumps(cv))
os.environ["TWILIO_WA_CONTENT_LAYOUT"] = "none"
ntw.send_whatsapp("+919800000002", "free text", check_delivery=False, fields=fields)
check("P4 layout 'none' (a fixed Twilio-provided template): ContentSid only, no variables", FC.sent[-1]["content_sid"] and FC.sent[-1]["content_variables"] is None
      and FC.sent[-1]["body"] is None)
del os.environ["TWILIO_WA_CONTENT_SID"], os.environ["TWILIO_WA_CONTENT_LAYOUT"]
FC.fail_create["+919800000003"] = 21654
r = ntw.send_whatsapp("+919800000003", "free text", check_delivery=False)
check("P5 error 21654 gets a readable reason (only approved templates) and the code once, not 'Twilio error 21654 (Twilio error 21654)'",
      r["code"] == 21654 and r["reason"].startswith("this WhatsApp number only accepts approved message templates") and "Twilio error" not in r["reason"], r["reason"])
check("P6 21655 (invalid template id) and an unknown code (Twilio's own message is used) are readable too",
      "not valid for this Twilio account" in ntw.reason(21655) and ntw.reason(99999, "Unable to create record: Something specific") == "Something specific")

# ---- D. delete account -------------------------------------------------------------------------------------------------------------
r = cb.post("/api/me/delete", json={"password": "test password 1"})
with sqlite3.connect(TMP / "users.db") as cn:
    left = cn.execute("SELECT COUNT(*) FROM sent_alerts WHERE user_key=?", (f"u{ib}",)).fetchone()[0]
check("D1 deleting an account removes its WhatsApp number and its 'already sent' records", r.status_code == 200 and users.get(ib) is None and left == 0)

# ---- U. profile page (headless Chrome, own server on port 8039) ----------------------------------------------------------------------------
import test_pages_logged_in as P  # noqa: E402
P.PORT, P.DEVTOOLS = 8039, 9339
P.BASE = f"http://127.0.0.1:{P.PORT}"
P.TMP = TMP / "ui"; P.TMP.mkdir()
proc = P.start_server()
import subprocess  # noqa: E402
chrome = subprocess.Popen([P.CHROME, "--headless=new", "--disable-gpu", "--no-sandbox", f"--remote-debugging-port={P.DEVTOOLS}",
                           f"--user-data-dir={P.TMP / 'chrome'}", "--window-size=1366,900", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    import urllib.request
    for _ in range(60):
        try:
            page = next(t for t in json.loads(urllib.request.urlopen(f"http://127.0.0.1:{P.DEVTOOLS}/json", timeout=2).read()) if t["type"] == "page")
            break
        except Exception:
            time.sleep(0.5)
    tab = P.Tab(page["webSocketDebuggerUrl"])
    sess = P.api_session(first=True)
    with sqlite3.connect(P.TMP / "users.db") as cn:                                    # the server's own temporary users.db
        cn.execute("UPDATE users SET whatsapp='+918888888888', whatsapp_alerts=1, wa_last=?",
                   (json.dumps({"time": "2026-10-24T10:00:00", "ok": False, "code": 63016, "reason": ntw.REASONS[63016], "kind": "live alert"}),))
    tab.set_session(sess)
    tab.goto(P.BASE + "/profile.html")
    tab.wait("document.getElementById('waNumber').value !== ''")
    tab.pump(0.6)
    ui = tab.js("""(() => ({ num: waNumber.value, alerts: waAlerts.checked, last: waLast.textContent, note: document.querySelector('.note-box').textContent,
                             btn: !!document.getElementById('testWa') }))()""")
    check("U1 profile page: number, WhatsApp switch, sandbox note and 'Last WhatsApp delivery failed: 63016: <readable reason>' (code once)",
          ui["num"] == "+918888888888" and ui["alerts"] and "join twilio-trial" in ui["note"] and "Only ONE phone" in ui["note"]
          and "pre-approved template" in ui["note"] and ui["last"].startswith("Last WhatsApp delivery failed: 63016: outside the 24-hour window")
          and "Twilio error" not in ui["last"] and ui["btn"], json.dumps(ui)[:300])
    with sqlite3.connect(P.TMP / "users.db") as cn:
        cn.execute("UPDATE users SET wa_last=?", (json.dumps({"time": "2026-10-24T12:30:00", "ok": False, "code": 21654, "reason": ntw.REASONS[21654],
                                                             "kind": "test"}),))
    tab.goto(P.BASE + "/profile.html")
    tab.wait("document.getElementById('waNumber').value !== ''")
    tab.pump(0.6)
    t21 = tab.js("""(() => ({ text: waLast.textContent, cls: waLast.className, color: getComputedStyle(waLast).color }))()""")
    check("U4 last failure 21654 (trial template limit): grey note 'WhatsApp needs a paid Twilio account to send our alert text', not the red error",
          t21["text"].startswith("WhatsApp needs a paid Twilio account to send our alert text") and "err" not in t21["cls"] and "muted" in t21["cls"]
          and "failed" not in t21["text"] and t21["color"] not in ("rgb(180, 35, 24)", "rgb(255, 138, 138)"), json.dumps(t21))
    tab.js("document.getElementById('testWa').click()")
    tab.wait("document.getElementById('waMsg').textContent.includes('Accepted')", 10)
    tab.pump(0.4)
    check("U2 'Send test WhatsApp' on the page: accepted (fake), no JavaScript errors", "Accepted" in tab.js("waMsg.textContent") and not tab.errors, str(tab.errors))
    tab.js("waNumber.value = '98765'; document.querySelector('#profileForm button[type=submit]').click()")
    tab.pump(0.3)
    check("U3 the page refuses a number without the country code before saving", "international format" in tab.js("saveMsg.textContent"))
    tab.ws.close()
finally:
    chrome.kill(); proc.kill()
server_log = (P.TMP / "server.log").read_text(encoding="utf-8", errors="replace") if (P.TMP / "server.log").exists() else ""

# ---- S. no token anywhere ------------------------------------------------------------------------------------------------------------
haystacks = {"stdout of the alert runs": OUT.getvalue(), "WhatsApp log": (TMP / "whatsapp_log.jsonl").read_text(encoding="utf-8"),
             "API responses": "\n".join(RESPONSES), "test server log": server_log,
             "UI test WhatsApp log": (P.TMP / "whatsapp_log.jsonl").read_text(encoding="utf-8") if (P.TMP / "whatsapp_log.jsonl").exists() else ""}
leaks = [k for k, v in haystacks.items() if FAKE_TOKEN in v or (REAL_TOKEN and REAL_TOKEN in v) or "TWILIO_AUTH_TOKEN=" in v]
check("S1 the Twilio token (test token and the real one from .env) appears in no log, no output and no API response", not leaks, str(leaks))
check("S2 the real users.db was not touched", (REAL_DB.stat().st_mtime if REAL_DB.exists() else None) == real_db_before)

print()
print("ALL PASSED" if not failures else f"{len(failures)} FAILED: {failures}")
sys.exit(1 if failures else 0)
