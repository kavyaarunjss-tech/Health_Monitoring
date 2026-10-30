"""WhatsApp alerts through Twilio (second alert channel next to e-mail; see notify_email.py for the alert rules).

Credentials ONLY from the environment or .env (never in code, never printed or logged):
    TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_FROM (e.g. whatsapp:+17372508034, the Twilio sandbox number)

Twilio test mode (sandbox): a phone receives messages only after it sent "join twilio-trial" to the sandbox number, and only within 24 h of
its last message to that number. Twilio usually accepts a message first and reports such problems a few seconds later (error 63015 =
not joined, 63016 = outside the 24 h window), so every send is followed by a delivery-status check; the result is stored for the profile page.

Safety: with AQI_EMAIL_FAKE=1 or AQI_WHATSAPP_FAKE=1 (all tests and test servers) no Twilio client is ever created; messages go to an
in-memory fake (FAKE_CLIENT) that tests can tell to fail with a given error code.
Rate limit (real time, persisted): at most one WhatsApp message per AQI_WA_MIN_GAP_S (60) seconds and AQI_WA_PER_HOUR (10) per hour.
The log (data/whatsapp_log.jsonl, git-ignored) keeps time, masked number, status and Twilio error code: never the token or the text.
"""
import json
import os
import re
import threading
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = Path(os.environ.get("AQI_WHATSAPP_LOG_FILE", ROOT / "data" / "whatsapp_log.jsonl"))
RATE_FILE = Path(os.environ.get("AQI_WA_RATE_FILE", ROOT / "data" / "whatsapp_rate.json"))
MIN_GAP_S = float(os.environ.get("AQI_WA_MIN_GAP_S", 60))
PER_HOUR = int(os.environ.get("AQI_WA_PER_HOUR", 10))
CHECK_AFTER_S = float(os.environ.get("AQI_WA_CHECK_S", 8))        # delivery-status check this long after sending
FAKE = os.environ.get("AQI_EMAIL_FAKE") == "1" or os.environ.get("AQI_WHATSAPP_FAKE") == "1"
MAX_LEN = 599                                                     # messages stay UNDER 600 characters
E164 = re.compile(r"^\+[1-9]\d{7,14}$")
SANDBOX_NUMBER = "+1 737 250 8034"
SANDBOX_JOIN = "join twilio-trial"
REASONS = {
    21654: "this WhatsApp number only accepts approved message templates (set TWILIO_WA_CONTENT_SID in .env)",
    21655: "the template id (TWILIO_WA_CONTENT_SID) is not valid for this Twilio account",
    21656: "the template variables are not valid for this template",
    63027: "the template does not exist in this language",
    63028: "the number of template variables does not match the template",
    63015: f"this phone has not joined the Twilio sandbox: send '{SANDBOX_JOIN}' to {SANDBOX_NUMBER} on WhatsApp first",
    63016: f"outside the 24-hour window: send any WhatsApp message to {SANDBOX_NUMBER}, then try again",
    63007: "the sender (TWILIO_WHATSAPP_FROM) is not a WhatsApp-enabled Twilio number",
    63018: "Twilio rate limit for this sender reached; try later",
    63003: "the number cannot receive WhatsApp messages",
    21211: "the number is not a valid phone number",
    21614: "the number is not a valid mobile number",
    20003: "Twilio refused the request: wrong credentials, or a feature that a trial account cannot use",
    20404: "Twilio account or message not found (check TWILIO_ACCOUNT_SID)",
}


# ---------------------------------------------------------------- settings
def env():
    """Twilio settings from the environment first, then .env. Returned values are used only to talk to Twilio."""
    out = {}
    f = ROOT / ".env"
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                if k.strip().startswith("TWILIO_"):
                    out[k.strip()] = v.strip().strip('"')
    for k in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_WHATSAPP_FROM", "TWILIO_WA_CONTENT_SID", "TWILIO_WA_CONTENT_LAYOUT"):
        if os.environ.get(k):
            out[k] = os.environ[k]
    return out


def sender():
    return env().get("TWILIO_WHATSAPP_FROM") or "whatsapp:+17372508034"


def template():
    """(content_sid, layout) when a WhatsApp Content Template is configured, else (None, None) = free-form Body.
    layout "aqi5" = our own AQI alert template with 5 variables (station, forecast AQI + category, time, Likely/Possible, advice line);
    layout "none" = a fixed template without variables (e.g. one of Twilio's pre-approved trial templates: our alert text cannot be sent)."""
    e = env()
    sid = (e.get("TWILIO_WA_CONTENT_SID") or "").strip()
    if not sid:
        return None, None
    layout = (e.get("TWILIO_WA_CONTENT_LAYOUT") or "aqi5").strip().lower()
    return sid, (layout if layout in ("aqi5", "none") else "aqi5")


def configured():
    if FAKE:
        return True
    e = env()
    return bool(e.get("TWILIO_ACCOUNT_SID") and e.get("TWILIO_AUTH_TOKEN") and e.get("TWILIO_WHATSAPP_FROM", "").startswith("whatsapp:+"))


def normalize(number):
    return re.sub(r"[\s\-().]", "", str(number or ""))


def valid_number(number):
    return bool(E164.match(normalize(number)))


def mask(number):
    n = normalize(number)
    return n[:3] + "*" * max(0, len(n) - 7) + n[-4:] if len(n) > 7 else "***"


def reason(code, fallback=""):
    """Plain-language reason for a Twilio error code (the page shows it as '<code>: <reason>'); unknown codes use Twilio's own message."""
    try:
        if int(code) in REASONS:
            return REASONS[int(code)]
    except (TypeError, ValueError):
        pass
    msg = re.sub(r"^Unable to create record:\s*", "", str(fallback or "")).strip()
    return msg or "unknown error"


def _var(s, limit=1024):
    """A WhatsApp template variable: one line (no newlines / tabs / long runs of spaces), at most `limit` characters."""
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s if len(s) <= limit else s[:limit - 1].rstrip() + "\u2026"


def content_variables(fields, layout):
    """ContentVariables JSON for the template layout ('aqi5'), or None when the template has no variables."""
    if layout != "aqi5" or not fields:
        return None
    keys = ("station", "aqi", "time", "level", "advice")
    return json.dumps({str(i + 1): _var(fields.get(k, "")) for i, k in enumerate(keys)})


# ---------------------------------------------------------------- fake client (tests / test servers): never talks to Twilio
class _FakeMessage:
    def __init__(self, sid, status, error_code=None):
        self.sid, self.status, self.error_code = sid, status, error_code


class FakeClient:
    """Records messages instead of sending. Tests may set fail_create[to] = code (Twilio rejects at once) or fail_later[to] = code
    (accepted, then 'undelivered' with that code at the status check)."""
    def __init__(self):
        self.sent, self.fail_create, self.fail_later, self._n, self._status = [], {}, {}, 0, {}
        outer = self

        class _Messages:
            def create(self, from_, to, body=None, content_sid=None, content_variables=None):
                n = to.replace("whatsapp:", "")
                if n in outer.fail_create:
                    from twilio.base.exceptions import TwilioRestException
                    raise TwilioRestException(400, "fake://twilio", msg="fake rejection", code=outer.fail_create[n])
                outer._n += 1
                sid = f"SMfake{outer._n:06d}"
                outer.sent.append({"from": from_, "to": to, "body": body, "sid": sid, "content_sid": content_sid,
                                   "content_variables": content_variables})
                outer._status[sid] = ("undelivered", outer.fail_later[n]) if n in outer.fail_later else ("delivered", None)
                return _FakeMessage(sid, "queued")

            def __call__(self, sid):
                class _Ctx:
                    def fetch(_self):
                        st, code = outer._status.get(sid, ("delivered", None))
                        return _FakeMessage(sid, st, code)
                return _Ctx()

        self.messages = _Messages()

    def reset(self):
        self.__init__()


FAKE_CLIENT = FakeClient()


def _client():
    if FAKE:
        return FAKE_CLIENT
    from twilio.rest import Client                       # imported only for real sending
    e = env()
    return Client(e["TWILIO_ACCOUNT_SID"], e["TWILIO_AUTH_TOKEN"])


# ---------------------------------------------------------------- rate limit (real time, persisted, separate from e-mail)
class RateLimited(Exception):
    def __init__(self, message, retry_after):
        super().__init__(message)
        self.retry_after = retry_after


_rate_lock = threading.Lock()


def reserve_slot(now=None):
    """Reserve one WhatsApp message slot before sending (1 per MIN_GAP_S, PER_HOUR per hour). Raises RateLimited(retry_after)."""
    now = time.time() if now is None else now
    with _rate_lock:
        try:
            times = [float(x) for x in json.loads(RATE_FILE.read_text(encoding="utf-8"))]
        except Exception:
            times = []
        times = [x for x in times if 0 <= now - x < 3600]
        if times and now - max(times) < MIN_GAP_S:
            raise RateLimited(f"WhatsApp messages are limited to one per {MIN_GAP_S:.0f} s", MIN_GAP_S - (now - max(times)))
        if len(times) >= PER_HOUR:
            raise RateLimited(f"WhatsApp limit reached ({PER_HOUR} per hour)", 3600 - (now - min(times)))
        times.append(now)
        RATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        RATE_FILE.write_text(json.dumps(times), encoding="utf-8")


# ---------------------------------------------------------------- log (no token, no message text, masked number)
_log_lock = threading.Lock()


def _log(entry):
    entry = {"time": datetime.now().isoformat(timespec="seconds"), **entry}
    with _log_lock:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")


# ---------------------------------------------------------------- sending
_checks = []


def send_whatsapp(to, text, on_result=None, kind="alert", check_delivery=True, fields=None):
    """Send one WhatsApp message. Returns {"ok": bool, "sid", "status", "code", "reason"} for the immediate answer from Twilio.
    on_result(ok, code, reason) is called with the FINAL result: at once if Twilio rejected the message, otherwise after the delivery-status
    check (CHECK_AFTER_S later, in a background thread; errors such as 63015 / 63016 only appear there).
    With TWILIO_WA_CONTENT_SID set the message is sent as that Content Template (ContentSid, plus ContentVariables built from `fields`
    for the 'aqi5' layout); otherwise as free-form Body `text`."""
    n = normalize(to)
    if not E164.match(n):
        res = {"ok": False, "sid": None, "status": "invalid", "code": None, "reason": "the number is not in international format (e.g. +919876543210)"}
        _log({"kind": kind, "to": mask(n), "status": "invalid"})
        if on_result:
            on_result(False, None, res["reason"])
        return res
    body = text if len(text) <= MAX_LEN else text[:MAX_LEN - 1] + "\u2026"
    sid_tpl, layout = template()
    if sid_tpl:
        params = {"content_sid": sid_tpl}
        cv = content_variables(fields, layout)
        if cv:
            params["content_variables"] = cv
    else:
        params = {"body": body}
    try:
        msg = _client().messages.create(from_=sender(), to="whatsapp:" + n, **params)
    except Exception as e:                                  # TwilioRestException carries the Twilio error code; never log the exception text
        code = getattr(e, "code", None)
        res = {"ok": False, "sid": None, "status": "rejected", "code": code,
               "reason": reason(code, getattr(e, "msg", "")) if code else f"could not reach Twilio ({type(e).__name__})"}
        _log({"kind": kind, "to": mask(n), "status": "rejected", "code": code})
        if on_result:
            on_result(False, code, res["reason"])
        return res
    _log({"kind": kind, "to": mask(n), "status": msg.status, "sid": msg.sid, "mode": "template" if sid_tpl else "text"})
    res = {"ok": True, "sid": msg.sid, "status": msg.status, "code": None, "reason": ""}
    if check_delivery:
        t = threading.Thread(target=_check, args=(msg.sid, n, on_result, kind), daemon=True)
        _checks.append(t)
        t.start()
    elif on_result:
        on_result(True, None, "")
    return res


def _check(sid, n, on_result, kind):
    time.sleep(CHECK_AFTER_S)
    try:
        m = _client().messages(sid).fetch()
        status, code = m.status, m.error_code
        detail = getattr(m, "error_message", "") or ""
    except Exception as e:
        status, code, detail = "unknown", getattr(e, "code", None), ""
    ok = status not in ("failed", "undelivered")
    _log({"kind": kind, "to": mask(n), "status": status, "sid": sid, "code": code})
    if on_result:
        on_result(ok, code, "" if ok else reason(code, detail or status))


def wait_checks(timeout=30):
    """Wait for the pending delivery-status checks (a short-lived process such as the hourly alert run must not exit before them)."""
    end = time.time() + timeout
    for t in list(_checks):
        t.join(max(0.0, end - time.time()))


# ---------------------------------------------------------------- message text
def alert_fields(mode, station_name, level, f, advice_line, issued, escalation=""):
    """The 5 values of the AQI alert template ('aqi5' layout), one short line each."""
    tag = "[REPLAY DEMO] " if mode == "replay" else ""
    upd = "UPDATE, " if escalation else ""
    aqi = f"AQI {f['aqi']} ({f['category']})" + (f", could reach {f['range_high']} ({f['category_high']})" if level == "possible" else "")
    return {"station": tag + station_name, "aqi": aqi, "time": f"hour ending {f['target_end']} (+{f['horizon']} h), issued {issued}",
            "level": upd + ("Likely" if level == "likely" else "Possible"), "advice": advice_line}


TEMPLATE_BODY = ("Air quality alert ({{4}}) for {{1}}: forecast {{2}} for the {{3}}. {{5}} "
                 "Not medical advice; in an emergency call 112.")
def compose(mode, station_name, level, f, advice_line, issued, escalation=""):
    """Short plain-text alert (no links, < 600 characters): station, forecast AQI, category, time, likely/possible, one advice line."""
    tag = "[REPLAY DEMO] " if mode == "replay" else ""
    upd = ("UPDATE, higher category: " if escalation == "category" else "UPDATE, higher alert level: " if escalation == "level" else "")
    kind = "Likely AQI alert" if level == "likely" else "Possible AQI alert"
    head = f"{tag}{upd}{kind}: {station_name}"
    fc = f"Forecast AQI {f['aqi']} ({f['category']}) for the hour ending {f['target_end']} (+{f['horizon']} h), issued {issued}."
    if level == "possible":
        fc += f" Could reach {f['range_high']} ({f['category_high']})."
    tail = "Not medical advice. Emergency: 112." + (" Simulated replay, not current air." if mode == "replay" else "")
    room = MAX_LEN - len(head) - len(fc) - len(tail) - 3
    adv_line = advice_line if len(advice_line) <= room else advice_line[:max(0, room - 1)].rstrip() + "…"
    return "\n".join([head, fc, adv_line, tail])[:MAX_LEN]
