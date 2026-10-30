"""Tests for the replay-demo e-mail rate limit and outbox (real-time, server side). No real e-mail is sent.

History
  2026-10-16 (1): five [REPLAY DEMO] e-mails went out within two minutes although the limit was 1 per 60 s. Cause: the send time was recorded only
      AFTER the slow SMTP call, so simultaneous requests all passed. Fix: reserve a slot under a lock BEFORE sending (reserve_replay_slot).
  2026-10-16 (2): at 6 h/s through the 24 Apr Silk Board spike the "Poor" / "UPDATE, higher category" e-mail never arrived: it hit the limit (429)
      and the page's single retry was skipped. Fix: e-mails are QUEUED in a server-side outbox and sent when a slot is free, highest priority first
      (escalation, then category), even if the pop-up has been replaced.

usage (project root, aqi env):  python backend\\test_email_rate_limit.py
"""
import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="aqi_ratetest_"))
os.environ.update({"AQI_EMAIL_FAKE": "1", "AQI_RATE_FILE": str(TMP / "rate.json"), "AQI_PROFILE_FILE": str(TMP / "profile.json"),
                   "AQI_MAIL_MIN_GAP_S": "60", "AQI_MAIL_PER_HOUR": "10"})
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))
import notify_email as ne  # noqa: E402

failures = []


def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  {extra}" if extra else ""))
    if not cond:
        failures.append(name)


def fresh():
    with ne._rate_lock:                                   # never race a worker thread that is reading the rate file (Windows file lock)
        ne.RATE_FILE.write_text("[]", encoding="utf-8")


# ---- Z. safety: in fake mode the REAL send() must never touch SMTP (2026-10-16: test runs sent 11 real e-mails because this guard was missing) ----
real_send = ne.send


class _NoSMTP:
    def __init__(self, *a, **k):
        raise AssertionError("real SMTP connection attempted in fake mode")


ne.smtplib.SMTP_SSL = _NoSMTP
try:
    ok = real_send("[TEST] must not be sent", "body", "someone@example.com")
    check("Z1 real send() in fake mode returns without touching SMTP", ok is True)
except AssertionError as e:
    check("Z1 real send() in fake mode returns without touching SMTP", False, f"({e})")
check("Z2 the outbox reports fake mode (so test scripts can verify it before running)", ne.ReplayOutbox().status().get("fake") is True)

# ---- A. the rate-limit rules, with synthetic clock values ----------------------------------------------------------------
fresh()
t0 = 1_000_000.0
ne.reserve_replay_slot(t0)
try:
    ne.reserve_replay_slot(t0 + 30)
    check("A1 second e-mail 30 s later is refused", False)
except ne.RateLimited as e:
    check("A1 second e-mail 30 s later is refused", True, f"(retry in {e.retry_after:.0f} s)")
ne.reserve_replay_slot(t0 + 61)
check("A2 an e-mail 61 s after the previous one is allowed", True)
fresh()
for i in range(10):
    ne.reserve_replay_slot(t0 + i * 61)
try:
    ne.reserve_replay_slot(t0 + 10 * 61)
    check("A3 the 11th e-mail within one hour is refused", False)
except ne.RateLimited:
    check("A3 the 11th e-mail within one hour is refused", True)
ne.reserve_replay_slot(t0 + 3601)
check("A4 after the oldest slot expires (1 h) sending is allowed again", True)
fresh()

# ---- B. race: 8 threads at the same instant -> exactly one slot ----------------------------------------------------------
res = []
gate = threading.Barrier(8)


def worker():
    gate.wait()
    try:
        ne.reserve_replay_slot()
        res.append("ok")
    except ne.RateLimited:
        res.append("limited")


ts = [threading.Thread(target=worker) for _ in range(8)]
[t.start() for t in ts]
[t.join() for t in ts]
check("B 8 simultaneous requests reserve exactly one slot", res.count("ok") == 1, f"(ok={res.count('ok')}, limited={res.count('limited')})")

# ---- C. outbox: escalation is never dropped, outdated e-mails are not sent ---------------------------------------------------
# Scenario from the 6 h/s replay: a Moderate e-mail goes out; while the limit blocks, a Moderate (newer) and a Poor escalation are queued.
fresh()
ne.MIN_GAP_S = 1.5                       # shorten the real-time gap for the test (the rules were verified above with 60 s)
sent_at = []


def fake_send(subject, body, to, dry_run=False):
    sent_at.append((time.time(), subject))
    return True


ne.send = fake_send
ob = ne.ReplayOutbox()
ob.enqueue("MOD-1", "b", "x", "silkboard", "likely", 2, 150, False)       # sent at once (slot free)
time.sleep(0.4)
ob.enqueue("MOD-2", "b", "x", "silkboard", "likely", 2, 160, False)       # waits for the slot
ob.enqueue("MOD-3", "b", "x", "silkboard", "likely", 2, 170, False)       # replaces MOD-2 (same station, category and level)
r = ob.enqueue("POOR-ESC", "b", "x", "silkboard", "likely", 3, 250, True)  # higher category: supersedes MOD-3 and goes first
check("C1 the escalation (Poor) is accepted while the limit is blocking", r.get("queued") is True)
deadline = time.time() + 8
while time.time() < deadline and len(sent_at) < 2:
    time.sleep(0.1)
order = [s for _, s in sent_at]
check("C2 Moderate goes out first, the Poor escalation next (after the gap)", order[:2] == ["MOD-1", "POOR-ESC"], f"(order {order})")
time.sleep(2.5)                           # give a wrongly kept MOD-2 / MOD-3 the chance to appear
order = [s for _, s in sent_at]
check("C3 outdated Moderate e-mails (MOD-2, MOD-3) are superseded and never sent", order == ["MOD-1", "POOR-ESC"], f"(sent {order}, dropped {ob.status()['dropped']})")
gaps = [b[0] - a[0] for a, b in zip(sent_at, sent_at[1:])]
check("C4 the real-time gap between sends is respected", all(g >= ne.MIN_GAP_S - 0.05 for g in gaps), f"(gaps {[round(g, 2) for g in gaps]} s)")
if ob.worker is not None:
    ob.worker.join(5)
fresh()
ob3 = ne.ReplayOutbox()
ob3.enqueue("FIRST", "b", "x", "silkboard", "likely", 2, 150, False)        # sent at once
time.sleep(0.3)
ob3.enqueue("POOR-PENDING", "b", "x", "silkboard", "likely", 3, 250, True)   # waits for the slot
r = ob3.enqueue("MOD-LATE", "b", "x", "silkboard", "likely", 2, 140, False)
check("C5 a lower-category e-mail is not queued behind a pending higher one", r.get("queued") is False, f"({r})")
if ob3.worker is not None:
    ob3.worker.join(8)

# priority across stations: escalation first, then higher category
fresh()
sent_at.clear()
ob2 = ne.ReplayOutbox()
ob2.enqueue("HEBBAL-MOD", "b", "x", "hebbal", "likely", 2, 140, False)          # sent at once
time.sleep(0.3)
ob2.enqueue("MYSURU-MOD", "b", "x", "mysuru", "likely", 2, 150, False)
ob2.enqueue("JAY-POOR", "b", "x", "jayanagar", "likely", 3, 210, False)
ob2.enqueue("SILK-ESC", "b", "x", "silkboard", "likely", 2, 130, True)          # an escalation outranks a higher category without the flag
deadline = time.time() + 12
while time.time() < deadline and len(sent_at) < 4:
    time.sleep(0.1)
order = [s for _, s in sent_at]
if ob2.worker is not None:
    ob2.worker.join(8)
check("C6 priority across stations: escalation first, then higher category", order == ["HEBBAL-MOD", "SILK-ESC", "JAY-POOR", "MYSURU-MOD"], f"(order {order})")

# ---- D. through the real HTTP endpoint with a SLOW fake send (this is the shape of the original failure) --------------------------------
fresh()
ne.MIN_GAP_S = 1.5
ne.OUTBOX = ne.ReplayOutbox()
from fastapi.testclient import TestClient  # noqa: E402
import backend.app as appmod  # noqa: E402

sent_at.clear()


def slow_send(subject, body, to, dry_run=False):
    time.sleep(1.0)                      # SMTP login + send takes seconds in real life
    sent_at.append((time.time(), subject))
    return True


ne.send = slow_send
ne.PROFILE.write_text(json.dumps({"groups": ["lung"], "station": "silkboard", "alert_from": 101, "email": "x@example.com"}), encoding="utf-8")
client = TestClient(appmod.app)
body = {"period": "validation", "station": "silkboard", "t": "2026-04-17 08:00:00"}
codes = []


def post():
    codes.append(client.post("/api/email/replay-alert", json=body).status_code)


ts = [threading.Thread(target=post) for _ in range(6)]
[t.start() for t in ts]
[t.join() for t in ts]
check("D1 six simultaneous HTTP requests are all accepted (queued), none is lost to a 429", codes.count(200) == 6, f"({sorted(codes)})")
time.sleep(0.3)
check("D2 but only ONE e-mail has gone out so far", len(sent_at) <= 1, f"(sent {len(sent_at)})")
time.sleep(5)
gaps = [b[0] - a[0] for a, b in zip(sent_at, sent_at[1:])]
check("D3 the identical alerts collapse to at most 2 e-mails, spaced by the real-time gap",
      len(sent_at) <= 2 and all(g >= ne.MIN_GAP_S - 0.05 for g in gaps), f"(sent {len(sent_at)}, gaps {[round(g, 2) for g in gaps]})")
st = client.get("/api/email/outbox").json()
check("D4 /api/email/outbox reports the sent and dropped e-mails", len(st["sent"]) == len(sent_at) and st["pending"] == [], f"({len(st['sent'])} sent, {len(st['dropped'])} dropped)")

# ---- E. e-mail wording: "higher category" only when the CPCB category rose; "higher alert level" for possible -> likely within a category ----
fc = {"aqi": 150, "category": "Moderate", "dominant": "pm10", "range_low": 120, "range_high": 190, "category_low": "Moderate", "category_high": "Moderate",
      "tier": "high", "horizon": 6, "target_end": "2026-04-24 08:00"}
prof = {"groups": ["lung"], "alert_from": 101}
subj_cat, _ = ne.compose_alert("replay", "Silk Board", "likely", fc, prof, "issued", escalation="category")
subj_lvl, _ = ne.compose_alert("replay", "Silk Board", "likely", fc, prof, "issued", escalation="level")
subj_none, _ = ne.compose_alert("replay", "Silk Board", "likely", fc, prof, "issued", escalation="")
check("E1 category escalation says 'UPDATE, higher category'", "UPDATE, higher category" in subj_cat and "[REPLAY DEMO]" in subj_cat, f"({subj_cat[:70]})")
check("E2 possible->likely within a category says 'UPDATE, higher alert level'", "UPDATE, higher alert level" in subj_lvl and "higher category" not in subj_lvl, f"({subj_lvl[:70]})")
check("E3 a normal alert has no UPDATE prefix", "UPDATE" not in subj_none)

print("\nALL PASSED" if not failures else f"\n{len(failures)} FAILED: {failures}")
sys.exit(1 if failures else 0)
