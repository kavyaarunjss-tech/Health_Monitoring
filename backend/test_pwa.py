"""PWA + Web Push channel tests (26 Oct 2026). NEVER sends real push notifications, e-mails or WhatsApp messages:
  * AQI_EMAIL_FAKE=1 -> notify_push uses its in-memory FakeWebPush; in addition pywebpush.webpush, smtplib and the Twilio client are replaced by
    classes that raise, so any attempt to reach a push service, Gmail or Twilio fails the test;
  * test VAPID keys are generated here (never the real ones in .env);
  * the API runs in-process (TestClient); the browser part runs its own server on port 8046 (DevTools 9346), never port 8000.
Covers: manifest and icons, service worker (cache-first static, network-first /api, offline copy marked with its time), the offline banner,
installability, install help (Android prompt / iPhone steps), tunnel safety (test-only switches and admin actions local only, Secure cookies on
https, host allow-list), the push channel rules (subscribe, test, replay queue, live alerts, shared cooldown, own sent-record and rate limit,
stale-data rule, failure isolation, expired-subscription cleanup) and that no key, endpoint or device secret appears in logs, output or responses.
Screenshots: screenshots_preview/pwa/.
usage (project root, aqi env):  python backend\\test_pwa.py
"""
import base64
import contextlib
import io
import json
import os
import re
import smtplib
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

ROOT = Path(__file__).resolve().parents[1]
TMP = Path(tempfile.mkdtemp(prefix="aqi_pwa_"))
OUTDIR = ROOT / "screenshots_preview" / "pwa"
OUTDIR.mkdir(parents=True, exist_ok=True)
_k = ec.generate_private_key(ec.SECP256R1())
B64 = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=").decode()          # noqa: E731
TEST_PRIV = B64(_k.private_numbers().private_value.to_bytes(32, "big"))
TEST_PUB = B64(_k.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint))
os.environ.update(AQI_EMAIL_FAKE="1", AQI_USERS_DB=str(TMP / "users.db"), AQI_SECRET_KEY="pwa-test-" + "p" * 40,
                  AQI_EMAIL_STATE_FILE=str(TMP / "email_state.json"), AQI_EMAIL_LOG_FILE=str(TMP / "email_log.jsonl"),
                  AQI_RATE_FILE=str(TMP / "rate.json"), AQI_PROFILE_FILE=str(TMP / "profile.json"), AQI_MAIL_MIN_GAP_S="0", AQI_MAIL_PER_HOUR="1000",
                  AQI_WHATSAPP_LOG_FILE=str(TMP / "whatsapp_log.jsonl"), AQI_WA_RATE_FILE=str(TMP / "wa_rate.json"),
                  AQI_PUSH_LOG_FILE=str(TMP / "push_log.jsonl"), AQI_PUSH_RATE_FILE=str(TMP / "push_rate.json"), AQI_PUSH_MIN_GAP_S="0",
                  AQI_PUSH_PER_HOUR="1000", VAPID_PUBLIC_KEY=TEST_PUB, VAPID_PRIVATE_KEY=TEST_PRIV, VAPID_SUBJECT="mailto:test@example.com")
sys.path.insert(0, str(ROOT / "backend"))


class NoNetwork:
    def __init__(self, *a, **k):
        raise AssertionError("a real push / SMTP / Twilio client was used in a test")


def no_webpush(*a, **k):
    raise AssertionError("pywebpush.webpush was called in a test")


import pywebpush  # noqa: E402
pywebpush.webpush = no_webpush
smtplib.SMTP_SSL = smtplib.SMTP = NoNetwork
import twilio.rest  # noqa: E402
twilio.rest.Client = NoNetwork

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402
import app as appmod  # noqa: E402
import advice as adv  # noqa: E402
import live_api  # noqa: E402
import notify_email as ne  # noqa: E402
import notify_push as npu  # noqa: E402
import users  # noqa: E402

failures, OUT, RESPONSES = [], io.StringIO(), []
REAL_EMAIL_LOG, REAL_PUSH_LOG = ROOT / "data" / "email_log.jsonl", ROOT / "data" / "push_log.jsonl"
real_before = {p: (p.stat().st_size if p.exists() else None) for p in (REAL_EMAIL_LOG, REAL_PUSH_LOG)}


def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  {extra}" if extra else ""))
    if not cond:
        failures.append(name)


emails, FAIL_EMAIL = [], set()


def fake_send(subject, body, to, dry_run=False):
    if to in FAIL_EMAIL:
        raise ConnectionError("simulated SMTP failure")
    emails.append({"to": to, "subject": subject})
    return True


ne.send = fake_send
FP = npu.FAKE_PUSH


def account(name, email, profile):
    c = TestClient(appmod.app)
    r = c.post("/api/auth/signup", json={"name": name, "email": email, "password": "test password 1", "consent": True})
    RESPONSES.append(r.text)
    r = c.put("/api/me", json=profile)
    RESPONSES.append(r.text)
    assert r.status_code == 200, r.text
    uid = users.session_user(c.cookies.get("aqi_session"))["id"]
    with sqlite3.connect(TMP / "users.db") as cn:
        cn.execute("UPDATE users SET email_verified=1 WHERE id=?", (uid,))
    return c, uid


def sub(n):
    return {"endpoint": f"https://fcm.googleapis.com/fcm/send/device-{n}-SECRET-ENDPOINT-0123456789",
            "keys": {"p256dh": f"BDEVICE{n}p256dhSECRETKEYVALUE0123456789", "auth": f"AUTH{n}SECRET0123"}}


# ---- A. manifest, icons, service worker ----------------------------------------------------------------------------------------------
man = json.loads((ROOT / "frontend" / "manifest.json").read_text(encoding="utf-8"))
icons = {(i["sizes"], i["purpose"]): i["src"] for i in man["icons"]}
sizes_ok, opaque = True, True
for (sz, purpose), src in icons.items():
    im = Image.open(ROOT / "frontend" / src.lstrip("/"))
    sizes_ok &= f"{im.size[0]}x{im.size[1]}" == sz
    if purpose == "maskable":
        opaque &= im.mode == "RGB"
check("A1 manifest: name 'AQ & Health Risk Framework', short name 'AQ Health', standalone, start_url and scope '/', site colours; icons 192/512 (any) and "
      "192/512 maskable (opaque, full-bleed), sizes match the files",
      man["name"] == "AQ & Health Risk Framework" and man["short_name"] == "AQ Health" and man["display"] == "standalone" and man["start_url"] == "/"
      and man["scope"] == "/" and man["theme_color"] == "#0b3c5d" and man["background_color"] == "#f4f6f9"
      and set(icons) == {("192x192", "any"), ("512x512", "any"), ("192x192", "maskable"), ("512x512", "maskable")} and sizes_ok and opaque, str(icons))
pages = [p for p in (ROOT / "frontend").glob("*.html") if not p.name.startswith("_")]
heads_ok = all(all(t in p.read_text(encoding="utf-8") for t in ('rel="manifest" href="/manifest.json"', 'name="theme-color" content="#0b3c5d"',
                                                                 'rel="apple-touch-icon" href="/icons/apple-touch-icon.png"')) for p in pages)
ati = Image.open(ROOT / "frontend" / "icons" / "apple-touch-icon.png")
check("A2 every page links the manifest, theme colour and the apple-touch-icon (180x180, no transparency)", heads_ok and ati.size == (180, 180) and ati.mode == "RGB",
      f"{len(pages)} pages")
c0 = TestClient(appmod.app)
sw, mf = c0.get("/sw.js"), c0.get("/manifest.json")
check("A3 /sw.js served at the site root as JavaScript (scope '/'), revalidated (no-cache); /manifest.json served",
      sw.status_code == 200 and "javascript" in sw.headers["content-type"] and sw.headers.get("cache-control") == "no-cache" and mf.status_code == 200)
src = sw.text
SWV = re.search(r'const VERSION = "(v\d+)"', src).group(1)          # cache names follow the service worker's VERSION
check("A4 service worker rules: /api network-first with the saved time and an offline marker; static cache-first; pages network-first; account, push and "
      "e-mail endpoints never cached; non-GET never intercepted",
      "networkFirstData" in src and "X-AQI-Offline" in src and "X-AQI-Saved-At" in src and "cacheFirst" in src and "networkFirstPage" in src
      and "/^\\/api\\/me(\\/|$)/" in src and "/^\\/api\\/push\\//" in src and "/^\\/api\\/email\\//" in src and 'req.method !== "GET"' in src)

# ---- B. tunnel safety ---------------------------------------------------------------------------------------------------------------
loc = c0.get("/?selftest=1", follow_redirects=False).status_code
tun = [c0.get("/?selftest=1", headers={h: v}, follow_redirects=False).status_code for h, v in
       (("X-Forwarded-For", "203.0.113.5"), ("CF-Connecting-IP", "203.0.113.5"), ("X-Forwarded-Proto", "https"))]
check("B1 the test-only ?selftest switch works on this computer but NOT through a tunnel (proxy headers -> login page)", loc == 200 and tun == [303, 303, 303], f"{loc} {tun}")
rn = c0.post("/api/scheduler/run-now", headers={"X-Forwarded-For": "203.0.113.5"}).status_code
check("B2 admin action 'run update now' is refused through a tunnel (403)", rn == 403, str(rn))
hs = TestClient(appmod.app, base_url="https://testserver")
r = hs.post("/api/auth/signup", json={"name": "Https", "email": "https@example.com", "password": "test password 1", "consent": True},
            headers={"Origin": "https://testserver"})
ck = r.headers.get("set-cookie", "")
hp = TestClient(appmod.app)
r2 = hp.post("/api/auth/signup", json={"name": "Http", "email": "http@example.com", "password": "test password 1", "consent": True})
ck2 = r2.headers.get("set-cookie", "")
g = hs.get("/?guest=1", follow_redirects=False).headers.get("set-cookie", "")
check("B3 on https the session cookie is Secure + HttpOnly + SameSite=Lax (and the guest cookie Secure + HttpOnly); on http://localhost not Secure",
      r.status_code == 200 and "Secure" in ck and "HttpOnly" in ck and "samesite=lax" in ck.lower() and "Secure" not in ck2 and "HttpOnly" in ck2
      and "Secure" in g and "HttpOnly" in g, f"{ck[:120]} | {ck2[:80]} | {g[:80]}")
code = ("import os,sys; sys.path.insert(0,'backend'); os.environ['AQI_ALLOWED_HOSTS']='localhost,127.0.0.1,*.trycloudflare.com';"
        "import app; from fastapi.testclient import TestClient as T;"
        "print(T(app.app, base_url='http://evil.example.com').get('/api/meta').status_code, T(app.app, base_url='https://abc.trycloudflare.com').get('/api/meta').status_code)")
hostp = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, env=dict(os.environ, AQI_USERS_DB=str(TMP / "users_hosts.db")))
check("B4 AQI_ALLOWED_HOSTS: other host names refused (400), the tunnel host accepted (200)", hostp.stdout.split()[-2:] == ["400", "200"],
      hostp.stdout.strip()[-40:] or hostp.stderr.strip()[-300:])

# ---- C. push channel (mocked) -------------------------------------------------------------------------------------------------------
ca, ia = account("Asha", "asha@example.com", {"station": "silkboard", "conditions": ["lung"], "age": 40})
k = ca.get("/api/push/key").json()
check("C1 /api/push/key returns the VAPID PUBLIC key (configured)", k == {"configured": True, "key": TEST_PUB})
bad = ca.post("/api/me/push/subscribe", json={"subscription": {"endpoint": "http://example.com/x", "keys": {"p256dh": "a", "auth": "b"}}, "live": True})
ok1 = ca.post("/api/me/push/subscribe", json={"subscription": sub(1), "live": True, "replay": True})
st1 = ca.post("/api/me/push/status", json={"endpoint": sub(1)["endpoint"]}).json()
anon = TestClient(appmod.app).post("/api/me/push/subscribe", json={"subscription": sub(9), "live": True})
check("C2 subscribe: a non-https endpoint is refused (400), a browser subscription is stored per device with its switches; not logged in -> 401",
      bad.status_code == 400 and ok1.status_code == 200 and st1["subscribed"] and st1["live"] and st1["replay"] and anon.status_code == 401, f"{bad.status_code} {st1}")
FP.reset()
t1 = ca.post("/api/me/push/test", json={"endpoint": sub(1)["endpoint"]}).json()
check("C3 'Send test notification' reaches THIS device only, through the fake push service (pywebpush never called)",
      t1["sent"] and len(FP.sent) == 1 and FP.sent[0]["endpoint"] == sub(1)["endpoint"] and FP.sent[0]["data"]["title"] == "AQ Health: test notification", str(t1))
npu.MIN_GAP_S = 60
npu.RATE_FILE = TMP / "push_rate_unit.json"
t2 = ca.post("/api/me/push/test", json={"endpoint": sub(1)["endpoint"]})
t3 = ca.post("/api/me/push/test", json={"endpoint": sub(1)["endpoint"]})
ne.MIN_GAP_S, ne.RATE_FILE = 60, TMP / "rate_unit.json"
ne.reserve_replay_slot(now=time.time())
try:
    npu.reserve_slot(now=time.time() + 120); indep = True
except npu.RateLimited:
    indep = False
check("C4 own rate limit: a second push within 60 s -> 429 with Retry-After; an e-mail just sent does not block a push",
      t2.status_code == 200 and t3.status_code == 429 and "retry-after" in t3.headers and indep, f"{t2.status_code} {t3.status_code}")
npu.MIN_GAP_S, ne.MIN_GAP_S, ne.RATE_FILE = 0, 0, TMP / "rate.json"

# replay alert through the shared queue (push only: e-mail and WhatsApp off)
FP.reset(); emails.clear()
T_REPLAY = "2026-04-24 01:00:00"
rr = ca.post("/api/email/replay-alert", json={"period": "validation", "station": "silkboard", "t": T_REPLAY}).json()
for _ in range(60):
    if FP.sent:
        break
    time.sleep(0.1)
p = FP.sent[0]["data"] if FP.sent else {}
check("C5 replay alert (push only) is queued and delivered: '[REPLAY DEMO] <category> · AQI <n> · <station>', time, top action, tap opens that alert hour",
      rr.get("push", {}).get("queued") and p.get("title", "").startswith("[REPLAY DEMO] Poor · AQI ") and p["title"].endswith("Silk Board")
      and "hour ending 2026-04-24 08:00 (+6 h)" in p["body"] and "Lung disease:" in p["body"] and "Not medical advice" in p["body"]
      and p["url"] == "/?station=silkboard&period=validation&at=2026-04-24+01%3A00%3A00&pauseonalert=1" and not emails, json.dumps(p)[:260])
rr2 = ca.post("/api/email/replay-alert", json={"period": "validation", "station": "silkboard", "t": T_REPLAY}).json()
with sqlite3.connect(TMP / "users.db") as cn:
    modes = {r[0] for r in cn.execute("SELECT mode FROM sent_alerts WHERE user_key=?", (f"u{ia}",))}
check("C6 the same replay alert is never pushed twice (own 'already sent' record 'replay-push')", rr2.get("push", {}).get("duplicate") and "replay-push" in modes,
      f"{rr2} {modes}")

# live alerts: fake live data
LIVE = {"silkboard": {"age": 3, "aqi": 150, "high": 175, "obs": "2026-10-24 10:00"}, "hebbal": {"age": 20, "aqi": 160, "high": 190, "obs": "2026-10-23 17:00"}}


def fake_stations():
    return [{"id": k_, "age_hours": v["age"]} for k_, v in LIVE.items()]


def fake_state(st):
    v = LIVE[st]
    f = {"horizon": 6, "available": True, "status": "future", "aqi": v["aqi"], "range_low": v["aqi"] - 20, "range_high": v["high"],
         "category": adv.category_of(v["aqi"]), "category_high": adv.category_of(v["high"]), "target_end": "2026-10-24 16:00", "tier": "high", "dominant": "pm10"}
    return {"station_name": ne.STATIONS[st], "now": "2026-10-24 12:00", "age_hours": v["age"], "forecasts": [f], "last_obs_end": v["obs"], "last_aqi": v["aqi"] - 5}


live_api.stations, live_api.state = fake_stations, fake_state
ca.put("/api/me", json={"replay_emails": False})
cb, ib = account("Bala", "bala@example.com", {"station": "silkboard", "conditions": ["heart"], "age": 50, "email_alerts": True})
cb.post("/api/me/push/subscribe", json={"subscription": sub(2), "live": True, "replay": False})
cc, ic = account("Chitra", "chitra@example.com", {"station": "hebbal", "conditions": ["lung"], "age": 30})
cc.post("/api/me/push/subscribe", json={"subscription": sub(3), "live": True})
FP.reset(); emails.clear()
with contextlib.redirect_stdout(OUT):
    ne.run_live()
to = sorted(x["endpoint"] for x in FP.sent)
lp = next((x["data"] for x in FP.sent if x["endpoint"] == sub(1)["endpoint"]), {})
check("C7 live: push-only user -> push; e-mail + push user -> both; title without [REPLAY DEMO], tap opens the live page of that station",
      to == sorted([sub(1)["endpoint"], sub(2)["endpoint"]]) and [m["to"] for m in emails] == ["bala@example.com"]
      and lp.get("title") == "Moderate · AQI 150 · Silk Board" and lp.get("url") == "/live.html?station=silkboard", f"{to} {lp}")
check("C8 stale-data rule: a station whose newest data is 20 h old (> 12 h) gets no push", sub(3)["endpoint"] not in to)
FP.reset(); emails.clear()
with contextlib.redirect_stdout(OUT):
    ne.run_live()
check("C9 second run within 12 h: no push and no e-mail (one cooldown shared by all channels)", not FP.sent and not emails, f"{FP.sent} {emails}")
with sqlite3.connect(TMP / "users.db") as cn:
    mb = {r[0] for r in cn.execute("SELECT mode FROM sent_alerts WHERE user_key=?", (f"u{ib}",))}
check("C10 the 'already sent' record has a separate entry per channel (live / live-push)", mb == {"live", "live-push"}, str(mb))
# failure isolation + expired subscriptions
LIVE["silkboard"]["obs"] = "2026-10-24 11:00"
(TMP / "email_state.json").unlink()
cd, id_ = account("Dev", "dev@example.com", {"station": "silkboard", "conditions": ["lung"], "age": 40, "email_alerts": True})
cd.post("/api/me/push/subscribe", json={"subscription": sub(4), "live": True})
ce, ie = account("Esha", "esha@example.com", {"station": "silkboard", "conditions": ["lung"], "age": 40})
ce.post("/api/me/push/subscribe", json={"subscription": sub(5), "live": True})
ce.post("/api/me/push/subscribe", json={"subscription": sub(6), "live": True})
FP.reset(); emails.clear()
FP.fail[sub(4)["endpoint"]] = 500                     # Dev: push service error -> the e-mail must still go
FP.fail[sub(5)["endpoint"]] = 410                     # Esha phone 1: expired -> removed; phone 2 still gets it
FP.fail[sub(1)["endpoint"]] = 404                     # Asha: expired -> removed
with contextlib.redirect_stdout(OUT):
    ne.run_live()
with sqlite3.connect(TMP / "users.db") as cn:
    left = {r[0] for r in cn.execute("SELECT endpoint FROM push_subs")}
    dev_modes = {r[0] for r in cn.execute("SELECT mode FROM sent_alerts WHERE user_key=? AND issued='2026-10-24 11:00'", (f"u{id_}",))}
check("C11 failure isolation: a push error (500) does not stop the e-mail, and the push claim is released (can be retried)",
      "dev@example.com" in [m["to"] for m in emails] and dev_modes == {"live"}, f"{[m['to'] for m in emails]} {dev_modes}")
check("C12 expired subscriptions (404 / 410) are deleted; the user's other device still gets the alert",
      sub(1)["endpoint"] not in left and sub(5)["endpoint"] not in left and sub(4)["endpoint"] in left
      and sub(6)["endpoint"] in [x["endpoint"] for x in FP.sent], f"left={len(left)}")
FP.fail.clear()
cd.post("/api/me/delete", json={"password": "test password 1"})
with sqlite3.connect(TMP / "users.db") as cn:
    gone = not cn.execute("SELECT 1 FROM push_subs WHERE user_id=?", (id_,)).fetchone()
check("C13 deleting the account deletes its push subscriptions", gone)
logtxt = (TMP / "push_log.jsonl").read_text(encoding="utf-8") if (TMP / "push_log.jsonl").exists() else ""
blob = logtxt + OUT.getvalue() + "".join(RESPONSES) + json.dumps(t1) + json.dumps(st1)
secrets = [TEST_PRIV, *[sub(n)["endpoint"] for n in range(1, 7)], *[sub(n)["keys"]["p256dh"] for n in range(1, 7)], *[sub(n)["keys"]["auth"] for n in range(1, 7)]]
check("C14 no VAPID private key, endpoint URL or device key in the push log, the printed output or any API response (log keeps a short hash)",
      logtxt.count("\n") >= 5 and not [s_ for s_ in secrets if s_ in blob] and '"device": "' in logtxt, f"{logtxt.count(chr(10))} log lines")

# notification preview (the REAL replay payload)
_, info = ne.replay_compose("silkboard", T_REPLAY, "validation", {"groups": ["lung"], "alert_from": 101, "email": "asha@example.com"})
pp = info["push_payload"]
icon = (ROOT / "frontend" / "icons" / "icon-192.png").as_uri()
esc = lambda s_: s_.replace("&", "&amp;").replace("<", "&lt;")                   # noqa: E731
(OUTDIR / "notification_preview.html").write_text(
    "<!doctype html><meta charset='utf-8'><meta name='viewport' content='width=device-width'><body style='margin:0;background:#1f2937;font-family:Roboto,Arial,sans-serif'>"
    "<div style='padding:28px 12px'><p style='color:#cbd5e1;font-size:12px;margin:0 0 10px'>Preview (mock-up of an Android notification, drawn from the real payload)</p>"
    "<div style='background:#f8fafc;border-radius:18px;padding:14px 16px;box-shadow:0 4px 18px rgba(0,0,0,.35)'><div style='display:flex;gap:8px;align-items:center;"
    f"font-size:12px;color:#475569'><img src='{icon}' width='18' height='18' style='border-radius:4px'> AQ Health · now</div>"
    f"<div style='font-weight:700;font-size:15px;color:#0f1d2b;margin:8px 0 4px'>{esc(pp['title'])}</div><div style='font-size:14px;color:#334155;line-height:1.45'>"
    f"{esc(pp['body'])}</div></div></div></body>", encoding="utf-8")
(OUTDIR / "home_screen_preview.html").write_text(
    "<!doctype html><meta charset='utf-8'><meta name='viewport' content='width=device-width'><body style='margin:0;min-height:100vh;background:linear-gradient(160deg,#334155,#0f172a);"
    "font-family:Roboto,Arial,sans-serif'><p style='color:#cbd5e1;font-size:12px;margin:0;padding:24px 16px 0'>Preview (mock-up of an Android home screen after installing)</p>"
    "<div style='display:grid;grid-template-columns:repeat(4,1fr);gap:22px 8px;padding:28px 16px'>"
    + "".join("<div style='text-align:center'><div style='width:56px;height:56px;margin:auto;border-radius:16px;background:rgba(255,255,255,.18)'></div>"
              "<div style='color:#e2e8f0;font-size:11px;margin-top:6px'>App</div></div>" for _ in range(5))
    + f"<div style='text-align:center'><img src='{(ROOT / 'frontend' / 'icons' / 'icon-maskable-192.png').as_uri()}' width='56' height='56' style='border-radius:50%'>"
    "<div style='color:#fff;font-size:11px;margin-top:6px'>AQ Health</div></div></div></body>", encoding="utf-8")

# ---- D. browser: service worker, offline, install, profile switch -------------------------------------------------------------------
import test_pages_logged_in as P  # noqa: E402
P.PORT, P.DEVTOOLS = 8046, 9346
P.BASE = f"http://127.0.0.1:{P.PORT}"
P.TMP = TMP / "ui"; P.TMP.mkdir()
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
    sess = P.api_session(first=True)

    def size(w, h, mobile=False):
        tab.cmd("Emulation.setDeviceMetricsOverride", width=w, height=h, deviceScaleFactor=2 if mobile else 1, mobile=mobile)

    def shot(name):
        data = base64.b64decode(tab.cmd("Page.captureScreenshot", format="png")["data"])
        for _ in range(5):
            try:
                (OUTDIR / (name + ".tmp")).write_bytes(data); os.replace(OUTDIR / (name + ".tmp"), OUTDIR / name); break
            except OSError:
                time.sleep(0.5)

    size(390, 844, True)
    tab.set_session(sess)
    tab.goto(P.BASE + "/?pauseonalert=0")
    tab.wait("!!(navigator.serviceWorker && navigator.serviceWorker.controller)", 25)
    ctl = tab.js("!!navigator.serviceWorker.controller")
    tab.goto(P.BASE + "/?pauseonalert=0")                                   # every request now goes through the service worker (and is saved)
    tab.wait("!!document.getElementById('stationsCard').dataset.clock && !!document.getElementById('weeklyCard').dataset.clock", 30)
    tab.pump(2.0)
    check("D1 the service worker registers (scope '/') and controls the page", ctl and tab.js("navigator.serviceWorker.controller.scriptURL").endswith("/sw.js"))
    online = tab.js("(async () => { const r = await fetch('/api/meta'); return [r.ok, r.headers.get('X-AQI-Offline')]; })()")
    cached = tab.js("""(async () => { const c = await caches.open('aqi-data-%s'); const r = await c.match('/api/meta');
        return r ? r.headers.get('X-AQI-Saved-At') : null; })()""" % SWV)
    names = tab.js("caches.keys()")
    check("D2 network-first for /api: online answers come from the server (no offline marker) and a copy is saved with its time; static files in their own cache",
          online == [True, None] and cached and cached.endswith("Z") and "aqi-static-" + SWV in names and "aqi-data-" + SWV in names, f"{online} {cached} {names}")
    nocache = tab.js("""(async () => { await fetch('/api/auth/session'); const c = await caches.open('aqi-data-%s');
        return [!!(await c.match('/api/auth/session')), !!(await c.match('/api/me')), !!(await c.match('/api/push/key'))]; })()""" % SWV)
    check("D3 never cached: own account (/api/me) and push endpoints; only 'who is logged in' is kept for offline use", nocache == [True, False, False], str(nocache))
    inst = tab.cmd("Page.getInstallabilityErrors")
    check("D4 Chrome's installability check (DevTools Page.getInstallabilityErrors): no errors", inst.get("installabilityErrors") == [], json.dumps(inst)[:300])
    # install prompt (Android): the browser's event -> our button -> prompt()
    tab.js("""(() => { const e = new Event('beforeinstallprompt'); e.prompt = () => { window.__prompted = true; }; e.userChoice = Promise.resolve({ outcome: 'accepted' });
        window.dispatchEvent(e); })()""")
    tab.pump(0.3)
    vis = tab.js("!document.getElementById('installBtn').hidden")
    shot("install_button_android_phone.png")
    tab.js("document.getElementById('installBtn').click()")
    tab.pump(0.3)
    check("D5 Android: the browser's install event shows 'Install app' in the header; tapping it opens the browser's install prompt",
          vis and tab.js("!!window.__prompted") and tab.js("document.getElementById('installBtn').hidden"))
    # iPhone: no prompt event -> the button opens the 'Share > Add to Home Screen' steps
    tab.cmd("Emulation.setUserAgentOverride", userAgent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1")
    tab.goto(P.BASE + "/?pauseonalert=0")
    tab.wait("!!document.getElementById('installBtn') && !document.getElementById('installBtn').hidden", 20)
    tab.js("document.getElementById('installBtn').click()")
    try:
        tab.wait("!!document.getElementById('installHelp')", 10)
    except Exception:
        print("DEBUG", tab.errors, tab.js("[!!document.getElementById('installBtn'), document.getElementById('installBtn') && document.getElementById('installBtn').hidden, navigator.userAgent]"))
    tab.pump(0.4)
    ios = tab.js("(document.getElementById('installHelp') || {}).textContent") or ""
    shot("install_help_iphone.png")
    check("D6 iPhone: 'Install app' shows the steps 'Share' > 'Add to Home Screen' > 'Add' and says alerts need the installed app",
          "Share" in ios and "Add to Home Screen" in ios and "installed app" in ios)
    tab.cmd("Emulation.setUserAgentOverride", userAgent=tab.js("navigator.userAgent").replace("iPhone", "Linux; Android 14").replace("Mac OS X", "Pixel 8"))
    # profile: "Alerts on this phone" with a stubbed browser push manager (no real push service is contacted)
    tab.cmd("Page.addScriptToEvaluateOnNewDocument", source="""(() => {
      const sub = { endpoint: 'https://fcm.googleapis.com/fcm/send/BROWSER-TEST-DEVICE-0123456789', unsubscribe: async () => true,
                    toJSON() { return { endpoint: this.endpoint, keys: { p256dh: 'BBROWSERp256dhTESTKEY0123456789', auth: 'BROWSERAUTH01' } }; } };
      let has = false;
      if (window.PushManager) { PushManager.prototype.getSubscription = async function () { return has ? sub : null; };
                                PushManager.prototype.subscribe = async function () { has = true; return sub; }; }
      if (window.Notification) { Object.defineProperty(Notification, 'permission', { get: () => 'granted', configurable: true });
                                 Notification.requestPermission = async () => 'granted'; }
    })();""")
    size(1280, 900)
    tab.goto(P.BASE + "/profile.html")
    tab.wait("!!document.getElementById('pushLive') && !document.getElementById('pushLive').disabled && document.getElementById('waNumber') !== null", 25)
    tab.pump(1.0)
    tab.js("document.getElementById('pushLive').click()")
    tab.wait("document.getElementById('pushMsg').textContent.includes('Saved')", 15)
    with sqlite3.connect(P.TMP / "users.db") as cn:
        row = cn.execute("SELECT live, replay FROM push_subs WHERE endpoint LIKE '%BROWSER-TEST-DEVICE%'").fetchone()
    tab.js("document.getElementById('testPush').click()")
    tab.wait("document.getElementById('pushMsg').textContent.startsWith('Sent')", 15)
    tab.js("document.getElementById('pushMsg').scrollIntoView({block: 'center'})")
    tab.pump(0.3)
    shot("profile_alerts_on_this_phone.png")
    check("D7 profile: switching on 'Alerts on this phone' asks permission, subscribes and stores the device (live on, replay off); the test button sends",
          row == (1, 0) and tab.js("document.getElementById('pushMsg').textContent").startswith("Sent"), str(row))
    # ---- install button: drawn icon, readable in light AND dark mode, never inside the installed app ------------------------------------
    from contrast_scan import ALLTEXT_JS
    size(390, 844, True)
    looks = {}
    for mode in ("light", "dark"):
        tab.cmd("Emulation.setEmulatedMedia", features=[{"name": "prefers-color-scheme", "value": mode}])
        tab.goto(P.BASE + "/?pauseonalert=0")
        tab.wait("!!document.getElementById('installBtn')", 20)
        tab.js("""(() => { const e = new Event('beforeinstallprompt'); e.prompt = () => {}; e.userChoice = Promise.resolve({}); window.dispatchEvent(e); })()""")
        tab.pump(0.4)
        looks[mode] = tab.js("""(() => { const b = document.getElementById('installBtn'), i = b.querySelector('.ib-ico'), cs = getComputedStyle(b);
            return { text: b.textContent.trim(), shown: !b.hidden && cs.display !== 'none', mask: i ? (getComputedStyle(i).maskImage || getComputedStyle(i).webkitMaskImage) : '',
                     opacity: cs.opacity, bg: cs.backgroundColor }; })()""")
        looks[mode]["fails"] = [f for f in tab.js(ALLTEXT_JS)["fails"] if "install" in f["where"].lower() or f["where"].startswith("span")]
        if mode == "dark":
            shot("install_button_dark_phone.png")
    check("D12 'Install' button: drawn download icon (no font glyph that could show as a box), solid (not looking disabled), readable in light and dark mode",
          all(v["shown"] and v["text"] in ("Install", "Install app", "Install app") and "svg" in v["mask"] and v["opacity"] == "1"
              and v["bg"] == "rgb(255, 255, 255)" and not v["fails"] for v in looks.values()), json.dumps(looks)[:400])
    tab.cmd("Emulation.setEmulatedMedia", features=[{"name": "prefers-color-scheme", "value": "light"}])
    sid = tab.cmd("Page.addScriptToEvaluateOnNewDocument", source="Object.defineProperty(navigator, 'standalone', { get: () => true, configurable: true });")["identifier"]
    tab.goto(P.BASE + "/?pauseonalert=0")
    tab.wait("!!document.getElementById('installBtn')", 20)
    tab.js("""(() => { const e = new Event('beforeinstallprompt'); e.prompt = () => {}; e.userChoice = Promise.resolve({}); window.dispatchEvent(e); })()""")
    tab.pump(0.4)
    sa = tab.js("[document.documentElement.classList.contains('standalone'), getComputedStyle(document.getElementById('installBtn')).display]")
    tab.cmd("Page.removeScriptToEvaluateOnNewDocument", identifier=sid)
    css = (ROOT / "frontend" / "style.css").read_text(encoding="utf-8")
    check("D13 inside the installed app (standalone) the Install button is never shown, even if the browser fires its install event "
          "(class 'standalone' + CSS @media (display-mode: standalone))",
          sa == [True, "none"] and "@media (display-mode: standalone) { .install-btn { display: none !important; } }" in css, str(sa))
    tab.cmd("Emulation.setEmulatedMedia", features=[])
    # ---- notification icons: colour 'AQ' icon + monochrome badge (Android draws the status-bar badge from its alpha channel only) ------------
    bim = Image.open(ROOT / "frontend" / "icons" / "badge-96.png")
    px = list(bim.getdata()) if hasattr(bim, "getdata") else []
    vis = [q for q in px if q[3] > 0]
    ico = Image.open(ROOT / "frontend" / "icons" / "icon-192.png").convert("RGB")
    check("D14 badge-96.png is a monochrome mask: 96x96 RGBA, only white pixels on a transparent background (the 'AQ' shape); icon-192.png keeps its colours",
          bim.size == (96, 96) and bim.mode == "RGBA" and vis and all(q[:3] == (255, 255, 255) for q in vis) and sum(q[3] == 0 for q in px) > len(px) * 0.5
          and len(set(ico.getdata())) > 10, f"{bim.mode} {bim.size} {len(vis)} visible px")
    swsrc = (ROOT / "frontend" / "sw.js").read_text(encoding="utf-8")
    events = []
    orig_event = tab._event

    def keep(msg):
        if str(msg.get("method", "")).startswith("ServiceWorker."):
            events.append(msg)
        orig_event(msg)
    tab._event = keep
    tab.cmd("Browser.grantPermissions", permissions=["notifications"], origin=P.BASE)
    tab.goto(P.BASE + "/?pauseonalert=0")
    tab.wait("!!(navigator.serviceWorker && navigator.serviceWorker.controller)", 20)
    tab.cmd("ServiceWorker.enable")
    tab.pump(1.0)
    regs = [r for e_ in events if e_["method"] == "ServiceWorker.workerRegistrationUpdated" for r in e_["params"]["registrations"] if not r.get("isDeleted")]
    reg_id = regs[0]["registrationId"] if regs else None
    shown = None
    if reg_id:
        tab.cmd("ServiceWorker.deliverPushMessage", origin=P.BASE, registrationId=reg_id,
                data=json.dumps({"title": "Test badge", "body": "x", "url": "/", "tag": "aqi-test"}))
        tab.pump(1.5)
        shown = tab.js("""(async () => { const r = await navigator.serviceWorker.ready; const ns = await r.getNotifications({ tag: 'aqi-test' });
            return ns.map(n => ({ title: n.title, icon: n.icon, badge: n.badge })); })()""")
    tab.cmd("ServiceWorker.disable")
    tab._event = orig_event
    check("D15 the service worker passes BOTH: icon = the colour 'AQ' icon, badge = the monochrome badge (source, and a real push delivered through DevTools)",
          'icon: "/icons/icon-192.png"' in swsrc and 'badge: "/icons/badge-96.png"' in swsrc and bool(shown)
          and shown[0]["icon"].endswith("/icons/icon-192.png") and shown[0]["badge"].endswith("/icons/badge-96.png"), f"reg={reg_id} shown={shown}")
    # installed look at phone size (standalone)
    size(390, 844, True)
    try:
        tab.cmd("Emulation.setEmulatedMedia", features=[{"name": "display-mode", "value": "standalone"}])
    except Exception:
        pass
    tab.goto(P.BASE + "/?pauseonalert=0")
    tab.wait("!!document.getElementById('stationsCard').dataset.clock", 30)
    tab.pump(1.0)
    shot("app_standalone_phone.png")
    tab.goto((OUTDIR / "home_screen_preview.html").as_uri()); tab.pump(0.6); shot("home_screen_phone.png")
    tab.goto((OUTDIR / "notification_preview.html").as_uri()); tab.pump(0.6); shot("notification_preview_phone.png")
    check("D8 no JavaScript errors while online", not tab.errors, str(tab.errors))
    # offline: the server stops (laptop off / no network) -> saved copy with its time, never shown as current
    tab.goto(P.BASE + "/?pauseonalert=0")
    tab.wait("!!document.getElementById('stationsCard').dataset.clock && !!document.getElementById('weeklyCard').dataset.clock", 30)
    tab.pump(2.0)
    saved = tab.js("""(async () => { const c = await caches.open('aqi-data-%s'); const r = await c.match('/api/meta'); return r.headers.get('X-AQI-Saved-At'); })()""" % SWV)
    proc.kill(); proc.wait(10)
    tab.errors.clear()
    tab.goto(P.BASE + "/?pauseonalert=0")
    tab.wait("!!document.getElementById('offlineBar') && !document.getElementById('offlineBar').hidden", 30)
    tab.pump(2.5)
    off = tab.js("""(() => ({ bar: document.getElementById('offlineBar').textContent, title: document.getElementById('stationTitle').textContent,
        aqi: document.getElementById('nowAqi').textContent, styled: getComputedStyle(document.querySelector('.topbar')).backgroundColor,
        cls: document.documentElement.className }))()""")
    expect = tab.js("(s) => fmtLocal(s)".replace("(s) =>", "((s) =>") + ")(%s)" % json.dumps(saved))
    shot("offline_banner_phone.png")
    check("D9 offline: the page still opens (pages and static files from the cache), shows the saved data, styled",
          off["title"] not in ("", "-") and off["aqi"] not in ("", "-") and off["styled"] not in ("", "rgba(0, 0, 0, 0)"), json.dumps(off)[:200])
    check("D10 offline banner: 'Offline - showing data from <time of the saved copy>', says it is NOT current; numbers dimmed",
          off["bar"].startswith("Offline - showing data from " + expect) and "NOT current" in off["bar"] and "is-offline" in off["cls"], f"{off['bar'][:140]} / {expect}")
    tab.cmd("Emulation.setEmulatedMedia", features=[{"name": "prefers-color-scheme", "value": "dark"}])
    tab.pump(0.5)
    shot("offline_banner_dark_phone.png")
    od = tab.js(ALLTEXT_JS)
    check("D10b offline banner (and the page under it) readable in dark mode (WCAG AA)", not od["fails"], json.dumps(od["fails"][:3]))
    tab.cmd("Emulation.setEmulatedMedia", features=[])
    srv = tab.js("(() => { const e = document.getElementById('serverDown'); return e ? e.hidden : true; })()")
    check("D11 with a saved copy on screen only the offline banner shows (no 'run python -m uvicorn' bar on a phone)", srv is True, str(srv))
    tab.ws.close()
finally:
    chrome.kill()
    try:
        proc.kill()
    except Exception:
        pass

# ---- E. Lighthouse (if installed) -------------------------------------------------------------------------------------------------
try:
    lh = subprocess.run("npx --no-install lighthouse --version", shell=True, capture_output=True, text=True, timeout=60)
    lh_ver = lh.stdout.strip() if lh.returncode == 0 else None
except Exception:
    lh_ver = None
print(f"INFO Lighthouse: {'version ' + lh_ver if lh_ver else 'not installed'}; its PWA category was removed in Lighthouse 12, so installability is checked "
      "with Chrome's own DevTools check (D4).")
check("Z1 nothing reached the real e-mail log or push log (sizes unchanged)",
      all((p_.stat().st_size if p_.exists() else None) == real_before[p_] for p_ in real_before))
print()
print("ALL PASSED" if not failures else f"{len(failures)} FAILED: {failures}")
sys.exit(1 if failures else 0)
