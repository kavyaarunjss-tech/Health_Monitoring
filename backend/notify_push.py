"""Web Push alert channel (phone / browser notifications), next to e-mail and WhatsApp. Added 26 Oct 2026.

* VAPID keys only from the environment or .env (VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY, VAPID_SUBJECT=mailto:...; created by
  backend/make_vapid_keys.py). The private key is never printed or logged.
* Subscriptions are stored per device in data/users.db (table push_subs, see users.py). A subscription endpoint is a secret capability URL: it
  is never logged either; the log keeps a short hash of it.
* Same rules as the other channels (see notify_email.run_live / ReplayOutbox): one 12 h cooldown per user and station shared by all channels,
  the stale-data rule, its own "already sent" record (modes 'live-push' / 'replay-push'), its own rate limit (1 per 60 s, 10 per hour,
  data/push_rate.json), failure isolation. A push service answer 404 or 410 means the subscription expired: it is deleted.
* Tests: AQI_EMAIL_FAKE=1 (or AQI_PUSH_FAKE=1) -> FakeWebPush records the notifications; pywebpush is never called.
Log: data/push_log.jsonl (time, user id, endpoint hash, ok, HTTP status, kind) - never keys, endpoints or notification text.
"""
import hashlib
import json
import os
import threading
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = Path(os.environ.get("AQI_PUSH_LOG_FILE", ROOT / "data" / "push_log.jsonl"))
RATE_FILE = Path(os.environ.get("AQI_PUSH_RATE_FILE", ROOT / "data" / "push_rate.json"))
MIN_GAP_S = float(os.environ.get("AQI_PUSH_MIN_GAP_S", "60"))
PER_HOUR = int(os.environ.get("AQI_PUSH_PER_HOUR", "10"))
FAKE = os.environ.get("AQI_EMAIL_FAKE") == "1" or os.environ.get("AQI_PUSH_FAKE") == "1"
TTL_S = 6 * 3600                       # the push service keeps an undelivered notification for at most 6 h (an alert is useless later)


def env():
    """VAPID settings from the environment, else from .env (values never printed)."""
    vals = {}
    f = ROOT / ".env"
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                vals[k.strip()] = v.strip().strip('"').strip("'")
    for k in ("VAPID_PUBLIC_KEY", "VAPID_PRIVATE_KEY", "VAPID_SUBJECT", "GMAIL_ADDRESS"):
        if os.environ.get(k):
            vals[k] = os.environ[k]
    return vals


def configured():
    e = env()
    return bool(e.get("VAPID_PUBLIC_KEY") and e.get("VAPID_PRIVATE_KEY"))


def public_key():
    return env().get("VAPID_PUBLIC_KEY", "")


def subject():
    e = env()
    return e.get("VAPID_SUBJECT") or ("mailto:" + e["GMAIL_ADDRESS"] if e.get("GMAIL_ADDRESS") else "mailto:admin@localhost")


def endpoint_id(endpoint):
    return hashlib.sha256(str(endpoint).encode()).hexdigest()[:12]


# ---------------------------------------------------------------- rate limit (real time, persisted, separate from e-mail / WhatsApp)
class RateLimited(Exception):
    def __init__(self, msg, retry_after):
        super().__init__(msg)
        self.retry_after = max(float(retry_after), 0.0)


_rate_lock = threading.Lock()


def reserve_slot(now=None):
    """Reserve one push slot before sending (1 per MIN_GAP_S, PER_HOUR per hour). Raises RateLimited(retry_after)."""
    now = time.time() if now is None else now
    with _rate_lock:
        try:
            times = [float(x) for x in json.loads(RATE_FILE.read_text(encoding="utf-8"))]
        except Exception:
            times = []
        times = [x for x in times if 0 <= now - x < 3600]
        if times and now - max(times) < MIN_GAP_S:
            raise RateLimited(f"Push notifications are limited to one per {MIN_GAP_S:.0f} s", MIN_GAP_S - (now - max(times)))
        if len(times) >= PER_HOUR:
            raise RateLimited(f"Push limit reached ({PER_HOUR} per hour)", 3600 - (now - min(times)))
        times.append(now)
        RATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        RATE_FILE.write_text(json.dumps(times), encoding="utf-8")


# ---------------------------------------------------------------- log (no keys, no endpoints, no text)
_log_lock = threading.Lock()


def _log(entry):
    entry = {"time": datetime.now().isoformat(timespec="seconds"), **entry}
    with _log_lock:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")


# ---------------------------------------------------------------- the notification
STATION_SHORT = {"silkboard": "Silk Board", "hebbal": "Hebbal", "jayanagar": "Jayanagar", "chikkaballapura": "Chikkaballapur",
                 "chikkamagaluru": "Chikkamagaluru", "mysuru": "Mysuru", "ramanagara": "Ramanagara", "madikeri": "Madikeri"}


def alert_payload(mode, station, station_name, level, f, top_action, issued, url, escalation=""):
    """Notification text: category + AQI + station + time + the top action (with its source). Replay alerts start with "[REPLAY DEMO]".
    The top action is the unchanged text of the first of the user's top 3 actions (advice.top_actions)."""
    tag = "[REPLAY DEMO] " if mode == "replay" else ""
    upd = {"category": "UPDATE, higher category: ", "level": "UPDATE, higher alert level: "}.get(escalation or "", "")
    name = STATION_SHORT.get(station, station_name)
    title = f"{tag}{upd}{f['category']} · AQI {f['aqi']} · {name}"
    kind = "Likely" if level == "likely" else "Possible"
    body = (f"{kind} for the hour ending {f['target_end']} (+{f['horizon']} h), issued {issued}."
            + (f" {top_action['text']} {top_action['source']}" if top_action else "") + " Not medical advice.")
    return {"title": title, "body": body, "url": url, "tag": f"aqi-{mode}-{station}", "mode": mode}


def test_payload():
    return {"title": "AQ Health: test notification", "body": "Notifications work on this device. Real alerts show the category, AQI, station, "
            "time and your top action.", "url": "/profile.html", "tag": "aqi-test", "mode": "test"}


# ---------------------------------------------------------------- sending
class FakeWebPush:
    """Tests: records notifications instead of sending. fail[endpoint] = HTTP status to simulate (404/410 expired, 500 error)."""
    def __init__(self):
        self.sent, self.fail = [], {}

    def reset(self):
        self.sent.clear(); self.fail.clear()

    def __call__(self, subscription_info, data, **kw):
        ep = subscription_info["endpoint"]
        if ep in self.fail:
            from pywebpush import WebPushException

            class Resp:
                status_code = self.fail[ep]
                text = ""
            raise WebPushException("simulated push failure", response=Resp())
        self.sent.append({"endpoint": ep, "data": json.loads(data), "ttl": kw.get("ttl")})
        return True


FAKE_PUSH = FakeWebPush()


def _webpush(info, data):
    if FAKE:
        return FAKE_PUSH(info, data, ttl=TTL_S)
    from pywebpush import webpush                          # the real push service call (never reached in tests)
    e = env()
    return webpush(subscription_info=info, data=data, vapid_private_key=e["VAPID_PRIVATE_KEY"], vapid_claims={"sub": subject()}, ttl=TTL_S)


def send_push(sub, payload, kind):
    """Send one notification to one stored subscription (a users.push_subs row). Returns {"ok", "status", "removed"}.
    404/410 = the subscription expired (the user removed the app / blocked notifications): it is deleted."""
    import users
    info = {"endpoint": sub["endpoint"], "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]}}
    try:
        _webpush(info, json.dumps(payload))
        users.set_push_status(sub["id"], True, 201, kind)
        _log({"user": sub["user_id"], "device": endpoint_id(sub["endpoint"]), "ok": True, "status": 201, "kind": kind})
        return {"ok": True, "status": 201, "removed": False}
    except Exception as e:                                   # WebPushException or network error: status code / type only, never details
        status = getattr(getattr(e, "response", None), "status_code", None)
        removed = status in (404, 410)
        if removed:
            users.delete_push_sub(sub["endpoint"])
        else:
            users.set_push_status(sub["id"], False, status or type(e).__name__, kind)
        _log({"user": sub["user_id"], "device": endpoint_id(sub["endpoint"]), "ok": False, "status": status or type(e).__name__, "kind": kind,
              "removed": removed})
        return {"ok": False, "status": status or type(e).__name__, "removed": removed}


def send_to_user(user_id, mode, payload, kind):
    """Send to every device of the user that has this mode ('live' / 'replay') switched on. Returns (number delivered, number of devices)."""
    import users
    subs = users.push_subs(user_id, mode)
    ok = sum(1 for s in subs if send_push(s, payload, kind)["ok"])
    return ok, len(subs)
