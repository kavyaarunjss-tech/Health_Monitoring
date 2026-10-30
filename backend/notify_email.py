"""E-mail alerts (Gmail SMTP with an app password stored in .env; never printed or logged).

.env lines (you add them yourself):  GMAIL_ADDRESS=...   GMAIL_APP_PASSWORD=...   ALERT_EMAIL_TO=...

Rules (same as the website):
  * Likely  = forecast AQI >= your alert level (up to +24 h);  Possible = only the upper end of the likely range reaches it (up to +12 h);
    nothing for +36 h and beyond. 12 h cooldown per station (escalation possible -> likely still sends).
  * LIVE mode: one check per user ACCOUNT with e-mail alerts on and a confirmed address (users.py, data/users.db), each with its own station,
    groups and alert level, sent to the account's own address; cooldown per user and station. NO alert e-mail when the newest observation at
    the user's station is older than 12 h; ONE "data feed stopped" notice per day (to ALERT_EMAIL_TO, the project owner) when every station is
    older than 24 h. The guest (browser) profile gets no live e-mails.
  * REPLAY mode (demo): subject starts with "[REPLAY DEMO]" and the body says the data is simulated.
  * REPLAY e-mails: a logged-in user's own profile and address (only if "replay-demo e-mails" is on and the address is confirmed); a guest
    uses data/profile.json (groups, station, alert_from, email; git-ignored) as before.

Usage (project root, aqi env):
  python backend\\notify_email.py --test                 send one clearly marked test e-mail
  python backend\\notify_email.py --live [--dry-run]     check live forecasts and send alert / feed-stopped e-mails
  python backend\\notify_email.py --replay-demo [--dry-run] [--station silkboard] [--time "2026-04-17 08:00:00"]
                                                          compose/send the e-mail a replay alert would send
"""
import argparse
import importlib
import json
import os
import re
import smtplib
import ssl
import sys
import threading
import time
from datetime import datetime, timedelta
from email.message import EmailMessage
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import advice as adv  # noqa: E402
import diurnal  # noqa: E402
import notify_twilio as ntw  # noqa: E402  (WhatsApp channel)
import notify_push as npu  # noqa: E402  (Web Push channel)

ROOT = Path(__file__).resolve().parents[1]
PROFILE = Path(os.environ.get("AQI_PROFILE_FILE", ROOT / "data" / "profile.json"))
RATE_FILE = Path(os.environ.get("AQI_RATE_FILE", ROOT / "data" / "replay_mail_rate.json"))
MIN_GAP_S = float(os.environ.get("AQI_MAIL_MIN_GAP_S", 60))        # replay-demo e-mails: at least this many REAL seconds apart
PER_HOUR = int(os.environ.get("AQI_MAIL_PER_HOUR", 10))            # ... and at most this many per real hour
FAKE = os.environ.get("AQI_EMAIL_FAKE") == "1"                      # tests only: pretend to send, never touch SMTP
STATE = Path(os.environ.get("AQI_EMAIL_STATE_FILE", ROOT / "data" / "email_state.json"))
LOG = Path(os.environ.get("AQI_EMAIL_LOG_FILE", ROOT / "data" / "email_log.jsonl"))
COOLDOWN = timedelta(hours=12)
POPUP_MAX_H = {"likely": 24, "possible": 12}
STALE_NO_ALERT_H = 12
FEED_NOTICE_H = 24
RANK = {"none": 0, "possible": 1, "likely": 2}
STATIONS = {"silkboard": "Silk Board, Bengaluru", "hebbal": "Hebbal, Bengaluru", "jayanagar": "Jayanagar 5th Block, Bengaluru",
            "chikkaballapura": "Chikkaballapur Rural", "chikkamagaluru": "Kalyana Nagara, Chikkamagaluru",
            "mysuru": "Hebbal 1st Stage, Mysuru", "ramanagara": "Vijay Nagar, Ramanagara", "madikeri": "Stuart Hill, Madikeri"}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ---------------------------------------------------------------- settings / profile
def env():
    out = {}
    f = ROOT / ".env"
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"')
    return out


def configured():
    if FAKE:
        return True
    e = env()
    return all(e.get(k) and not e[k].lower().startswith(("paste", "your")) for k in ("GMAIL_ADDRESS", "GMAIL_APP_PASSWORD", "ALERT_EMAIL_TO"))


def load_profile():
    try:
        p = json.loads(PROFILE.read_text(encoding="utf-8"))
    except Exception:
        p = {}
    return {"groups": [g for g in p.get("groups", []) if g in adv.VULNERABLE_GROUPS], "station": p.get("station") if p.get("station") in STATIONS else "silkboard",
            "alert_from": int(p.get("alert_from", 201)), "email": p.get("email") or ""}


def save_profile(p):
    """Store ONLY groups, station, alert_from, email (validated). Returns the stored dict."""
    clean = {"groups": [g for g in p.get("groups", []) if g in adv.VULNERABLE_GROUPS],
             "station": p.get("station") if p.get("station") in STATIONS else "silkboard"}
    vuln = bool(clean["groups"])
    default = adv.DEFAULT_ALERT["vulnerable" if vuln else "healthy"]
    clean["alert_from"] = max(1, min(int(p.get("alert_from", default)), default))          # may lower, never raise
    email = (p.get("email") or "").strip()
    if email and not EMAIL_RE.match(email):
        raise ValueError("invalid e-mail address")
    clean["email"] = email
    PROFILE.parent.mkdir(parents=True, exist_ok=True)
    PROFILE.write_text(json.dumps(clean, indent=1), encoding="utf-8")
    return clean


def recipient(profile):
    return profile.get("email") or env().get("ALERT_EMAIL_TO", "")


# ---------------------------------------------------------------- composing
def level_of(f, threshold):
    if f["aqi"] >= threshold:
        return "likely"
    if f["range_high"] >= threshold:
        return "possible"
    return "none"


def best_candidate(forecasts, threshold):
    best = None
    for f in forecasts:
        if not f.get("available", True) or f.get("status") == "past":
            continue
        lv = level_of(f, threshold)
        if lv == "none" or f["horizon"] > POPUP_MAX_H[lv]:
            continue
        if best is None or RANK[lv] > RANK[best[0]] or (lv == best[0] and f["aqi"] > best[1]["aqi"]):
            best = (lv, f)
    return best


def compose_alert(mode, station_name, level, f, profile, issued, data_age_h=None, period_note=None, escalation=False,
                  forecasts=None, now_aqi=None, seq=0, pattern=None):
    """forecasts / now_aqi: for the trend line; seq: alert number (advice.alert_number of the issue hour: same alert -> same tip);
    pattern: the station's typical time-of-day pattern (diurnal.py) for the best time to go out."""
    prof = {"groups": profile["groups"], "alert_from": profile["alert_from"]}
    pa = adv.personal_advice(f["aqi"], prof, forecasts, now_aqi, f.get("dominant"), seq, pattern)
    th = adv.thresholds(prof)["alert_from"]
    kind = "AQI alert (likely)" if level == "likely" else "Possible AQI alert"
    tag = "[REPLAY DEMO] " if mode == "replay" else ""
    if escalation:
        kind = ("UPDATE, higher alert level: " if escalation == "level" else "UPDATE, higher category: ") + kind
    subject = f"{tag}{kind}: {station_name} - AQI {f['aqi']} ({f['category']}) for {f['target_end']} (+{f['horizon']} h)"
    lines = []
    if mode == "replay":
        lines += ["*** REPLAY DEMO: this alert is SIMULATED from a past period. It is not about current air quality. ***", ""]
    lines += [f"{kind} for {station_name}", "",
              f"Issued: {issued}   For the hour ending: {f['target_end']} (+{f['horizon']} h after the last observation)",
              f"Forecast AQI: {f['aqi']} ({f['category']}" + (f", mainly {adv.pname(f['dominant'])}" if f.get("dominant") else "") + ")",
              f"Likely range: {f['range_low']} to {f['range_high']}   Your alert level: AQI {th}"]
    if level == "possible":
        lines.append(f"The forecast itself is below your alert level; only the upper end of the likely range reaches it (it could reach {f['range_high']}, {f['category_high']}). Possible alerts are more often false alarms.")
    tier = {"high": "High confidence", "medium": "Moderate confidence", "low": "Low confidence: tendency only"}[f["tier"]]
    lines.append(f"Confidence: {tier}.")
    if data_age_h is not None:
        lines.append(f"Data age: the newest observation is {data_age_h:.0f} hours old.")
    if period_note:
        lines.append(period_note)
    lines += ["", f"For you ({pa['category']}):"]
    for it in pa["full"]:
        lines.append(f"  - {it['text']} {it['source']}")
        if it["kind"] == "best_time" and pa.get("best_how"):
            lines.append(f"    ({pa['best_how']})")
    lines += ["", "Sources: " + "; ".join(f"[{k}] {v}" for k, v in adv.REFERENCES.items()), "",
              adv.DISCLAIMER, "", "These forecasts come from a student research prototype."]
    html = alert_html(mode, kind, station_name, level, f, pa, th, issued, tier, data_age_h, period_note)
    return subject, MailText("\n".join(lines), html)


# ---------------------------------------------------------------- HTML e-mail (26 Oct 2026; presentation only, same wording as the text part)
# Gmail-safe: inline CSS only, table layout, no <style>, no JavaScript, no SVG, no external CSS or images. The plain-text part stays the alternative.
class MailText(str):
    """the plain-text body (a normal str everywhere) that also carries its HTML version for send()."""
    def __new__(cls, text, html=None):
        o = super().__new__(cls, text)
        o.html = html
        return o


CAT_BG = {"Good": "#1a7f3c", "Satisfactory": "#9ccc3c", "Moderate": "#f5c400", "Poor": "#ef7d0f", "Very Poor": "#c62828", "Severe": "#7a1212"}
CAT_FG = {"Good": "#ffffff", "Satisfactory": "#0f1d2b", "Moderate": "#0f1d2b", "Poor": "#0f1d2b", "Very Poor": "#ffffff", "Severe": "#ffffff"}
FONT = "font-family:Arial,Helvetica,sans-serif;"
MUTED = "#566476"


def _esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _marked(s):
    """escaped text with **...** shown as <strong> (the bold markers come from advice.mark / the rule table)."""
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", _esc(s))


def _line(p):
    return _marked(p.get("marked") or p["text"]) + f' <span style="color:{MUTED};font-size:12px;">{_esc(p["source"])}</span>'


def _section(title, items, border, bg, head):
    if not items:
        return ""
    rows = "".join(f'<p style="margin:6px 0;font-size:14px;line-height:1.5;color:#0f1d2b;">{_line(p)}</p>' for p in items)
    return (f'<tr><td style="padding:6px 24px;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>'
            f'<td style="border-left:4px solid {border};background:{bg};padding:8px 12px;{FONT}">'
            f'<p style="margin:2px 0 4px;font-size:15px;font-weight:700;color:{head};">{_esc(title)}</p>{rows}</td></tr></table></td></tr>')


def alert_html(mode, kind, station_name, level, f, pa, th, issued, tier, data_age_h, period_note):
    cat = f["category"]
    bg, fg = CAT_BG.get(cat, "#566476"), CAT_FG.get(cat, "#ffffff")
    top = pa.get("top3") or []
    shown = {t for p in top for t in [p["text"], *p.get("covers", [])]}
    affect = [p for p in (pa.get("headline"), pa.get("pollutant")) if p]
    todo = [p for p in pa["full"] if p["kind"] not in ("headline", "pollutant") and p["text"] not in shown]
    out = [f'<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>'
           f'<body style="margin:0;padding:0;background:#f4f6f9;{FONT}">'
           f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f6f9;"><tr><td align="center" style="padding:16px 8px;">'
           f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;background:#ffffff;border-top:6px solid {bg};'
           f'border-radius:8px;{FONT}color:#0f1d2b;">']
    if mode == "replay":
        out.append('<tr><td style="background:#fff4d6;color:#5c4300;padding:10px 24px;font-size:13px;font-weight:700;">REPLAY DEMO: this alert is SIMULATED '
                   'from a past period. It is not about current air quality.</td></tr>')
    out.append(f'<tr><td style="padding:20px 24px 4px;"><p style="margin:0;font-size:13px;color:{MUTED};">{_esc(kind)}</p>'
               f'<p style="margin:2px 0 12px;font-size:20px;font-weight:700;">{_esc(station_name)}</p>'
               f'<table role="presentation" cellpadding="0" cellspacing="0"><tr>'
               f'<td style="background:{bg};color:{fg};font-weight:700;font-size:14px;padding:6px 14px;border-radius:14px;">{_esc(cat)}</td>'
               f'<td style="padding-left:12px;font-size:14px;">Forecast AQI <span style="font-size:28px;font-weight:700;">{f["aqi"]}</span></td></tr></table>'
               f'<p style="margin:8px 0 0;font-size:13px;color:{MUTED};">For the hour ending {_esc(f["target_end"])} (+{f["horizon"]} h) &middot; issued {_esc(issued)}'
               + (f' &middot; mainly {_esc(adv.pname(f["dominant"]))}' if f.get("dominant") else "") + '</p></td></tr>')
    if top:
        rows = "".join(f'<tr><td valign="top" style="padding:6px 10px 6px 0;width:24px;"><div style="width:24px;height:24px;line-height:24px;border-radius:12px;'
                       f'background:#0f6e78;color:#ffffff;text-align:center;font-weight:700;font-size:13px;">{i}</div></td>'
                       f'<td style="padding:6px 0;font-size:15px;line-height:1.5;">{_line(p)}</td></tr>' for i, p in enumerate(top, 1))
        out.append(f'<tr><td style="padding:16px 24px 4px;"><p style="margin:0 0 4px;font-size:16px;font-weight:700;">What to do now</p>'
                   f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0">{rows}</table></td></tr>')
    det = [f"Likely range: {f['range_low']} to {f['range_high']}", f"Your alert level: AQI {th}", f"Confidence: {tier}"]
    if level == "possible":
        det.append(f"The forecast itself is below your alert level; only the upper end of the likely range reaches it (it could reach {f['range_high']}, "
                   f"{f['category_high']}). Possible alerts are more often false alarms.")
    if data_age_h is not None:
        det.append(f"Data age: the newest observation is {data_age_h:.0f} hours old.")
    if period_note:
        det.append(period_note)
    out.append(f'<tr><td style="padding:12px 24px 4px;"><p style="margin:0 0 4px;font-size:16px;font-weight:700;">Details</p>' +
               "".join(f'<p style="margin:4px 0;font-size:14px;line-height:1.5;">{_esc(d)}</p>' for d in det) + '</td></tr>')
    out.append(_section("May affect you", affect, "#b45309", "#fff6e5", "#7a3e00"))
    out.append(_section("What you can do", todo, "#1a7f3c", "#ebf6ee", "#14532d"))
    if pa.get("best_how"):
        out.append(f'<tr><td style="padding:0 24px;font-size:12px;color:{MUTED};line-height:1.5;">{_esc(pa["best_how"])}</td></tr>')
    out.append(f'<tr><td style="padding:16px 24px 20px;font-size:12px;color:{MUTED};line-height:1.5;">'
               f'<p style="margin:0 0 6px;"><strong>Sources:</strong> ' + "; ".join(f"[{k}] {_esc(v)}" for k, v in adv.REFERENCES.items()) + '</p>'
               f'<p style="margin:0 0 6px;">{_esc(adv.DISCLAIMER)}</p><p style="margin:0;">These forecasts come from a student research prototype.</p></td></tr>')
    out.append('</table></td></tr></table></body></html>')
    return "".join(out)


def build_message(subject, body, to, sender):
    """the e-mail as sent: the plain-text part plus the HTML alternative (the designed HTML when the body carries one)."""
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = sender, to, subject
    msg.set_content(str(body))
    msg.add_alternative(getattr(body, "html", None) or to_html(str(body)), subtype="html")
    return msg


def to_html(text):
    esc = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return "<html><body><pre style=\"font-family:system-ui,Segoe UI,sans-serif;white-space:pre-wrap;font-size:14px\">" + esc + "</pre></body></html>"


# ---------------------------------------------------------------- sending
def send(subject, body, to, dry_run=False):
    """Send via Gmail SMTP (SSL). The app password is read from .env and is never printed."""
    if dry_run:
        print("--- DRY RUN (nothing sent) ---\nTo:", to, "\nSubject:", subject, "\n\n" + body, "\n------------------------------")
        return True
    if FAKE:                                  # tests only (AQI_EMAIL_FAKE=1): NEVER touch SMTP, even when .env holds real credentials
        return True
    e = env()
    if not configured():
        raise RuntimeError("E-mail is not configured: add GMAIL_ADDRESS, GMAIL_APP_PASSWORD and ALERT_EMAIL_TO to .env")
    msg = build_message(subject, body, to, e["GMAIL_ADDRESS"])
    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx, timeout=30) as s:
        s.login(e["GMAIL_ADDRESS"], e["GMAIL_APP_PASSWORD"].replace(" ", ""))
        s.send_message(msg)
    with open(LOG, "a", encoding="utf-8") as fh:                                 # log subject only: never the password or health profile
        fh.write(json.dumps({"time": datetime.now().isoformat(timespec="seconds"), "to": to, "subject": subject}) + "\n")
    return True


def send_test(dry_run=False):
    e = env()
    to = e.get("ALERT_EMAIL_TO", "(ALERT_EMAIL_TO)")
    body = ("This is a TEST e-mail from the Karnataka AQI forecast project (student research prototype).\n\n"
            "If you can read this, e-mail alerts are set up correctly. Real alerts will say 'AQI alert (likely)' or 'Possible AQI alert'; "
            "alerts from the replay demo start with [REPLAY DEMO].\n\n" + adv.DISCLAIMER)
    return send("[TEST] AQI alert system", body, to, dry_run)


# ---------------------------------------------------------------- state (cooldown, daily feed notice)
def load_state():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(s):
    STATE.write_text(json.dumps(s, indent=1), encoding="utf-8")


# ---------------------------------------------------------------- live mode
def run_live(dry_run=False):
    import live_api
    to = env().get("ALERT_EMAIL_TO", "")                # the daily "feed stopped" notice goes to the project owner (.env)
    state, now = load_state(), datetime.now()
    sts = live_api.stations()
    ages = {s["id"]: s.get("age_hours") for s in sts if s.get("age_hours") is not None}
    sent = 0
    # one daily notice if the feed has stopped (every station older than FEED_NOTICE_H)
    if ages and min(ages.values()) > FEED_NOTICE_H:
        if state.get("feed_notice_date") != now.strftime("%Y-%m-%d"):
            body = (f"The OpenAQ data feed looks stopped: the freshest station observation is {min(ages.values()):.0f} hours old "
                    f"(oldest {max(ages.values()):.0f} h). Live alert e-mails are paused until the data is less than {STALE_NO_ALERT_H} hours old.\n"
                    "This is one notice per day.\n\n" + adv.DISCLAIMER)
            send("AQI project: data feed stopped", body, to, dry_run)
            state["feed_notice_date"] = now.strftime("%Y-%m-%d")
            sent += 1
    # one check per ACCOUNT with live alerts on (e-mail with a confirmed address and/or WhatsApp with a number), each with its own station,
    # groups and alert level. ONE cooldown per user and station ("user<id>:<station>") shared by both channels; the stale-data rule applies
    # to both; each channel has its own "already sent" record (mode 'live' / 'live-whatsapp') and a failure on one never stops the other.
    # The guest browser profile gets no live alerts.
    import users
    users.init()
    accounts = users.alert_users()
    if not accounts:
        print("no accounts with live alerts on (e-mail with a confirmed address, or WhatsApp with a number): no alerts.")
    cache = {}
    for u in accounts:
        p, who = u["profile"], f"user {u['id']}"
        th = adv.thresholds(p)["alert_from"]
        st_id = p["station"]
        age = ages.get(st_id)
        if age is None:
            print(f"{who} {st_id}: no live data; no alert.")
            continue
        if age > STALE_NO_ALERT_H:
            print(f"{who} {st_id}: newest observation is {age:.0f} h old (> {STALE_NO_ALERT_H} h): no alert e-mail sent.")
            continue
        stt = cache.get(st_id) or cache.setdefault(st_id, live_api.state(st_id))
        cand = best_candidate(stt["forecasts"], th)
        if cand is None:
            print(f"{who} {st_id}: no forecast reaches the alert level (AQI {th}).")
            continue
        level, f = cand
        key = f"user{u['id']}:{st_id}"
        last = state.get(key)
        if last and now - datetime.fromisoformat(last["time"]) < COOLDOWN and RANK[level] <= RANK[last["level"]]:
            print(f"{who} {st_id}: {level} alert suppressed (cooldown).")
            continue
        issued, pattern = stt.get("last_obs_end", ""), _live_pattern(st_id, stt.get("last_obs_end"))
        delivered = False
        if u.get("email_on", True):
            claim = (users.sent_key(u["id"], u["email"]), "live", st_id, issued, f["target_end"], level)
            if not dry_run and not users.record_sent(*claim):
                print(f"{who} {st_id}: this alert was already e-mailed (same issue time, target and level): e-mail skipped.")
            else:
                subject, body = compose_alert("live", stt["station_name"], level, f, p, stt["now"], data_age_h=stt["age_hours"],
                                              forecasts=stt["forecasts"], now_aqi=stt.get("last_aqi"), seq=adv.alert_number(issued), pattern=pattern)
                try:
                    send(subject, body, u["email"], dry_run)
                    delivered = True
                    sent += 1
                except Exception as e:                  # this channel failed: release its claim, keep going with WhatsApp
                    if not dry_run:
                        users.unrecord_sent(*claim)
                    print(f"{who} {st_id}: e-mail failed ({type(e).__name__}); other channels continue.")
        if u.get("wa_on"):
            delivered |= _live_whatsapp(u, st_id, stt, level, f, p, issued, pattern, dry_run)
        if u.get("push_on"):
            delivered |= _live_push(u, st_id, stt, level, f, p, issued, pattern, dry_run)
        if delivered:
            state[key] = {"time": now.isoformat(timespec="seconds"), "level": level}
    if not dry_run:
        save_state(state)
    ntw.wait_checks(timeout=30)                          # let the WhatsApp delivery-status checks finish before the process exits
    print(f"done: {sent} e-mail(s) {'composed (dry run)' if dry_run else 'sent'}; {_WA_SENT[0]} WhatsApp message(s) "
          f"{'composed (dry run)' if dry_run else 'sent'}; {_PUSH_SENT[0]} push alert(s) {'composed (dry run)' if dry_run else 'sent'}.")


_WA_SENT = [0]
_PUSH_SENT = [0]


def _live_push(u, st_id, stt, level, f, p, issued, pattern, dry_run):
    """Live alert by Web Push to every device of the account with live alerts on. Returns True if at least one device got it."""
    import users
    who = f"user {u['id']}"
    if not npu.configured() and not npu.FAKE:
        print(f"{who} {st_id}: push is not configured (VAPID keys in .env); other channels continue.")
        return False
    claim = (users.sent_key(u["id"], "push"), "live-push", st_id, issued, f["target_end"], level)
    if not dry_run and not users.record_sent(*claim):
        print(f"{who} {st_id}: this alert was already sent as a push notification: skipped.")
        return False
    pa = adv.personal_advice(f["aqi"], {"groups": p["groups"], "alert_from": p["alert_from"]}, stt["forecasts"], stt.get("last_aqi"),
                             f.get("dominant"), adv.alert_number(issued), pattern)
    payload = npu.alert_payload("live", st_id, stt["station_name"], level, f, (pa.get("top3") or [None])[0], stt["now"],
                                "/live.html?station=" + st_id)
    if dry_run:
        print("--- DRY RUN push (nothing sent) ---\n" + payload["title"] + "\n" + payload["body"])
        _PUSH_SENT[0] += 1
        return True
    try:
        npu.reserve_slot()
    except npu.RateLimited as e:
        users.unrecord_sent(*claim)
        print(f"{who} {st_id}: push rate limit ({e}); will be tried at the next run.")
        return False
    ok, n = npu.send_to_user(u["id"], "live", payload, "live alert")
    if ok:
        _PUSH_SENT[0] += 1
        return True
    users.unrecord_sent(*claim)
    print(f"{who} {st_id}: push not delivered to any of {n} device(s); other channels continue.")
    return False


def _live_whatsapp(u, st_id, stt, level, f, p, issued, pattern, dry_run):
    """Live alert by WhatsApp for one account. Returns True if Twilio accepted the message (or a dry run composed it)."""
    import users
    who = f"user {u['id']}"
    claim = (users.sent_key(u["id"], u["whatsapp"]), "live-whatsapp", st_id, issued, f["target_end"], level)
    if not dry_run and not users.record_sent(*claim):
        print(f"{who} {st_id}: this alert was already sent by WhatsApp: skipped.")
        return False
    pa = adv.personal_advice(f["aqi"], {"groups": p["groups"], "alert_from": p["alert_from"]}, stt["forecasts"], stt.get("last_aqi"),
                             f.get("dominant"), adv.alert_number(issued), pattern)
    text = ntw.compose("live", stt["station_name"], level, f, _advice_line(pa), stt["now"])
    fields = ntw.alert_fields("live", stt["station_name"], level, f, _advice_line(pa), stt["now"])
    if dry_run:
        print("--- DRY RUN WhatsApp (nothing sent) ---\nTo:", ntw.mask(u["whatsapp"]), "\n" + text)
        _WA_SENT[0] += 1
        return True
    try:
        ntw.reserve_slot()
    except ntw.RateLimited as e:
        users.unrecord_sent(*claim)
        print(f"{who} {st_id}: WhatsApp rate limit ({e}); will be tried at the next run.")
        return False

    def done(ok, code, why):
        users.set_wa_status(u["id"], ok, code, why, kind="live alert")
        if not ok:
            users.unrecord_sent(*claim)
            print(f"{who} {st_id}: WhatsApp delivery failed: {why}")
    res = ntw.send_whatsapp(u["whatsapp"], text, on_result=done, kind="live alert", fields=fields)
    if res["ok"]:
        _WA_SENT[0] += 1
    else:
        print(f"{who} {st_id}: WhatsApp not sent: {res['reason']}; other channels continue.")
    return res["ok"]


def _live_pattern(station, last_obs_end):
    """Typical time-of-day pattern from the 28 days up to the newest observation (hour-start label = hour ending - 1 h)."""
    try:
        label = (datetime.strptime(str(last_obs_end)[:16], "%Y-%m-%d %H:%M") - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
        return diurnal.live_profile(station, label)
    except (ValueError, Exception):
        return None


# ---------------------------------------------------------------- account e-mails (verification link, password reset)
def send_account_link(kind, to, name, link):
    """kind 'verify' or 'reset'. The link holds a one-time token; it is not logged (send() logs only time/to/subject)."""
    if kind == "verify":
        subject = "AQI project: please confirm your e-mail address"
        body = (f"Hello {name},\n\nPlease confirm this e-mail address for your account on the Karnataka AQI forecast website "
                f"(student research prototype, running on a local computer):\n\n{link}\n\nThe link works once and expires in 24 hours. "
                "Alert e-mails are sent only to confirmed addresses.\n\nIf you did not create this account, ignore this e-mail.")
    else:
        subject = "AQI project: reset your password"
        body = (f"Hello {name},\n\nSomeone (hopefully you) asked to reset the password of your account on the Karnataka AQI forecast website.\n\n"
                f"{link}\n\nThe link works once and expires in 1 hour. If you did not ask for this, ignore this e-mail; your password stays the same.")
    return send(subject, body, to)


def forget_user(user_id, email):
    """Delete-account: remove this user's cooldown state, pending/sent outbox items and e-mail log lines."""
    s = load_state()
    s = {k: v for k, v in s.items() if not k.startswith(f"user{user_id}:")}
    if STATE.exists():
        save_state(s)
    OUTBOX.forget(user_id)
    if email and LOG.exists():
        keep = []
        for line in LOG.read_text(encoding="utf-8").splitlines():
            try:
                if json.loads(line).get("to", "").lower() == email.lower():
                    continue
            except Exception:
                pass
            keep.append(line)
        LOG.write_text("".join(x + "\n" for x in keep), encoding="utf-8")


# ---------------------------------------------------------------- replay-demo rate limit (REAL time, server side)
class RateLimited(Exception):
    def __init__(self, message, retry_after):
        super().__init__(message)
        self.retry_after = retry_after


_rate_lock = threading.Lock()


def reserve_replay_slot(now=None):
    """Reserve one replay-demo e-mail slot BEFORE sending. Thread-safe and persisted in RATE_FILE (survives restarts).
    The slot is consumed even if the send later fails, so a failing SMTP login cannot be hammered either.
    Raises RateLimited(retry_after seconds) when the previous slot is < MIN_GAP_S ago or PER_HOUR slots were used in the last hour."""
    now = time.time() if now is None else now
    with _rate_lock:
        try:
            times = [float(x) for x in json.loads(RATE_FILE.read_text(encoding="utf-8"))]
        except Exception:
            times = []
        times = [x for x in times if 0 <= now - x < 3600]
        if times and now - max(times) < MIN_GAP_S:
            raise RateLimited(f"Replay e-mails are limited to one per {MIN_GAP_S:.0f} s", MIN_GAP_S - (now - max(times)))
        if len(times) >= PER_HOUR:
            raise RateLimited(f"Replay e-mail limit reached ({PER_HOUR} per hour)", 3600 - (now - min(times)))
        times.append(now)
        RATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        RATE_FILE.write_text(json.dumps(times), encoding="utf-8")


def _app_module():
    """The already-loaded app module (uvicorn loads it as backend.app); importing it a second time would run it twice."""
    for name in ("backend.app", "app"):
        if name in sys.modules:
            return sys.modules[name]
    return importlib.import_module("app")


# ---------------------------------------------------------------- replay-demo outbox (queue + priority, drained at the rate limit)
class ReplayOutbox:
    """Replay-demo e-mails are QUEUED, never dropped by the rate limit. A worker thread sends the highest-priority pending e-mail whenever a
    real-time rate-limit slot is free. Priority: escalation first, then higher CPCB category, then level, then AQI.
    A pending e-mail is superseded (dropped) only when a newer e-mail for the SAME station has a higher category, or the same category and
    level (then the newest replaces it). A queued e-mail is sent even if the pop-up it came from has already been replaced."""
    MAX_PENDING = 20
    EXPIRE_S = 1800                                    # a pending e-mail older than 30 real minutes is stale and is dropped

    def __init__(self):
        self.lock = threading.Lock()
        self.items, self.sent, self.dropped, self.failed = [], [], [], []
        self.events = []                                   # (real time, event, subject): a timeline for tests and debugging
        self.worker = None
        self._seq = 0
        self.wake = threading.Event()                      # set by enqueue(): a worker waiting for a rate limit re-checks at once

    @staticmethod
    def priority(it):
        return (it["escalation"], it["cat_rank"], RANK[it["level"]], it["aqi"], -it["seq"])

    def enqueue(self, subject, body, to, station, level, cat_rank, aqi, escalation, owner=None, claim=None, channel="email", fields=None):
        """owner = user id of the account the e-mail belongs to (None = guest). Superseding compares only e-mails to the SAME address and
        station, so one user's alerts never replace another user's."""
        with self.lock:
            self._seq += 1
            self.events.append((time.time(), "enqueue", subject, owner))
            it = {"subject": subject, "body": body, "to": to, "station": station, "level": level, "cat_rank": cat_rank, "aqi": aqi,
                  "escalation": bool(escalation), "seq": self._seq, "t": time.time(), "owner": owner, "claim": claim, "channel": channel,
                  "fields": fields}

            def same(x):
                return x["station"] == station and x["to"] == to

            if any(same(x) and x["cat_rank"] > cat_rank for x in self.items):
                self.dropped.append((owner, subject))
                return {"queued": False, "reason": "a higher category is already waiting to be sent"}
            keep = []
            for x in self.items:
                if same(x) and (x["cat_rank"] < cat_rank or (x["cat_rank"] == cat_rank and x["level"] == level)):
                    self.dropped.append((x["owner"], x["subject"]))          # superseded by this newer / higher one
                else:
                    keep.append(x)
            keep.append(it)
            while len(keep) > self.MAX_PENDING:
                low = min(keep, key=self.priority)
                keep.remove(low)
                self.dropped.append((low["owner"], low["subject"]))
            self.items = keep
            self.wake.set()
            if self.worker is None or not self.worker.is_alive():
                self.worker = threading.Thread(target=self._run, daemon=True)
                self.worker.start()
            return {"queued": True, "pending": len(self.items), "subject": subject}

    def _run(self):
        while True:
            with self.lock:
                now = time.time()
                for x in [x for x in self.items if now - x["t"] > self.EXPIRE_S]:
                    self.items.remove(x)
                    self.dropped.append((x["owner"], x["subject"]))
                if not self.items:
                    return
            # highest priority first, but each channel has its own rate limit: a rate-limited (or failing) channel never blocks the other
            with self.lock:
                order = sorted(self.items, key=self.priority, reverse=True)
            it, waits = None, []
            for cand in order:
                try:
                    {"whatsapp": ntw.reserve_slot, "push": npu.reserve_slot}.get(cand.get("channel"), reserve_replay_slot)()
                    it = cand
                    break
                except (RateLimited, ntw.RateLimited, npu.RateLimited) as e:
                    waits.append(e.retry_after)
            if it is None:
                w = min(waits) if waits else 1.0
                self.events.append((time.time(), "wait", f"rate limit (retry in {w:.1f} s)", "all"))
                self.wake.clear()
                self.wake.wait(min(w, 5.0) + 0.1)                # woken early when something new is queued (e.g. an e-mail behind a waiting WhatsApp)
                continue
            with self.lock:
                if it not in self.items:                 # superseded while waiting
                    continue
                self.items.remove(it)
                self.events.append((time.time(), "popped", it["subject"], it["owner"]))
            if it.get("channel") == "whatsapp":
                self._send_whatsapp(it)
                continue
            if it.get("channel") == "push":
                self._send_push(it)
                continue
            try:
                send(it["subject"], it["body"], it["to"])
                self.sent.append((it["owner"], it["subject"]))
                self.events.append((time.time(), "sent", it["subject"], it["owner"]))
            except Exception as e:  # SMTP / login errors: record the type only, never credentials
                self.failed.append((it["owner"], (it["subject"], type(e).__name__)))
                if it.get("claim"):                    # not delivered: release the "already sent" claim so it may be sent later
                    import users
                    users.unrecord_sent(*it["claim"])

    def _send_whatsapp(self, it):
        import users

        def done(ok, code, why):                       # final result (after Twilio's delivery-status check)
            users.set_wa_status(it["owner"], ok, code, why, kind="replay alert")
            if not ok:
                with self.lock:
                    self.failed.append((it["owner"], (it["subject"], f"WhatsApp {code or ''} {why}".strip())))
                if it.get("claim"):
                    users.unrecord_sent(*it["claim"])
        res = ntw.send_whatsapp(it["to"], it["body"], on_result=done, kind="replay alert", fields=it.get("fields"))
        if res["ok"]:
            self.sent.append((it["owner"], it["subject"]))
            self.events.append((time.time(), "sent", it["subject"], it["owner"]))

    def _send_push(self, it):
        import users
        try:
            ok, n = npu.send_to_user(it["owner"], "replay", it["fields"]["payload"], "replay alert")
        except Exception as e:                                 # never let one channel stop the worker
            ok, n = 0, type(e).__name__
        if ok:
            self.sent.append((it["owner"], it["subject"]))
            self.events.append((time.time(), "sent", it["subject"], it["owner"]))
        else:
            with self.lock:
                self.failed.append((it["owner"], (it["subject"], f"push: no device reached ({n})")))
            if it.get("claim"):
                users.unrecord_sent(*it["claim"])

    def forget(self, owner):
        """Delete-account: remove every pending, sent, dropped and logged item of this user."""
        with self.lock:
            self.items = [x for x in self.items if x["owner"] != owner]
            self.sent = [x for x in self.sent if x[0] != owner]
            self.dropped = [x for x in self.dropped if x[0] != owner]
            self.failed = [x for x in self.failed if x[0] != owner]
            self.events = [x for x in self.events if x[3] != owner]

    def status(self, owner="all"):
        """owner='all' (tests, CLI) lists everything; a user id (or None for a guest) lists only that owner's e-mails."""
        def mine(o):
            return owner == "all" or o == owner or o == "all"
        with self.lock:
            return {"fake": FAKE, "pending": [x["subject"] for x in sorted(self.items, key=self.priority, reverse=True) if mine(x["owner"])],
                    "sent": [s for o, s in self.sent[-50:] if mine(o)], "dropped": [s for o, s in self.dropped[-50:] if mine(o)],
                    "failed": [f for o, f in self.failed[-20:] if mine(o)],
                    "events": [(round(t, 2), e, sub) for t, e, sub, o in self.events[-100:] if mine(o)]}


OUTBOX = ReplayOutbox()


# ---------------------------------------------------------------- replay demo
def replay_compose(station, t, period="validation", profile=None, escalation=False):
    """Compose the e-mail a replay alert would send at simulated time t (numbers recomputed on the server). None if no alert level is reached."""
    appmod = _app_module()
    profile = profile or load_profile()
    st = appmod.state(period, station, t)
    th = adv.thresholds({"groups": profile["groups"], "alert_from": profile["alert_from"]})["alert_from"]
    cand = best_candidate(st["forecasts"], th)
    if cand is None:
        return {"sent": False, "reason": f"no forecast reaches your alert level (AQI {th}) at this simulated hour"}, None
    level, f = cand
    subject, body = compose_alert("replay", st["station_name"], level, f, profile, st["sim_time_end"] + " (simulated)",
                                  period_note=f"Replay period: {period}; simulated time {st['sim_time_end']}.", escalation=escalation,
                                  forecasts=st["forecasts"], now_aqi=(st["now"] or {}).get("aqi"), seq=adv.alert_number(t),
                                  pattern=diurnal.replay_profile(station, t))
    pa = adv.personal_advice(f["aqi"], {"groups": profile["groups"], "alert_from": profile["alert_from"]}, st["forecasts"],
                             (st["now"] or {}).get("aqi"), f.get("dominant"), adv.alert_number(t), diurnal.replay_profile(station, t))
    wa_text = ntw.compose("replay", st["station_name"], level, f, _advice_line(pa), st["sim_time_end"] + " (simulated)", escalation or "")
    wa_fields = ntw.alert_fields("replay", st["station_name"], level, f, _advice_line(pa), st["sim_time_end"] + " (simulated)", escalation or "")
    from urllib.parse import urlencode
    push_payload = npu.alert_payload("replay", station, st["station_name"], level, f, (pa.get("top3") or [None])[0], st["sim_time_end"] + " (simulated)",
                                     "/?" + urlencode({"station": station, "period": period, "at": t, "pauseonalert": "1"}), escalation or "")
    info = {"subject": subject, "body": body, "to": recipient(profile), "level": level, "aqi": f["aqi"],
            "cat_rank": adv.ORDER.index(f["category"]), "station": station, "target": f["target_end"], "wa_text": wa_text, "wa_fields": wa_fields,
            "push_payload": push_payload}
    return None, info


def _advice_line(pa):
    """The one advice line of a WhatsApp alert: the first personal line (your health group, or what to do) with its citation."""
    first = (pa.get("short") or pa.get("full") or [{"text": "", "source": ""}])[0]
    return f"{first['text']} {first['source']}".strip()


def replay_enqueue_whatsapp(station, t, period, phone, profile, owner, escalation=False):
    """QUEUE the WhatsApp version of a replay alert for an account (same queue, priority, supersede rules and de-duplication as e-mail;
    its own rate limit). The 'already sent' record uses mode 'replay-whatsapp', so an e-mail never blocks the first WhatsApp of an alert."""
    import users
    users.init()
    res, info = replay_compose(station, t, period, profile, escalation)
    if info is None:
        return res
    claim = (users.sent_key(owner, phone), "replay-whatsapp", station, t, info["target"], info["level"])
    if not users.record_sent(*claim):
        return {"queued": False, "duplicate": True, "reason": "This alert was already sent to your WhatsApp (same station, issue time, target time and level)."}
    r = OUTBOX.enqueue("[WhatsApp] " + info["subject"], info["wa_text"], ntw.normalize(phone), station, info["level"], info["cat_rank"],
                       info["aqi"], escalation, owner=owner, claim=claim, channel="whatsapp", fields=info["wa_fields"])
    if not r.get("queued"):
        users.unrecord_sent(*claim)
    return r


def replay_enqueue_push(station, t, period, profile, owner, escalation=False):
    """QUEUE the push version of a replay alert for an account's devices with replay-demo alerts on (same queue, priority and supersede rules;
    its own rate limit and 'already sent' record, mode 'replay-push')."""
    import users
    users.init()
    res, info = replay_compose(station, t, period, profile, escalation)
    if info is None:
        return res
    claim = (users.sent_key(owner, "push"), "replay-push", station, t, info["target"], info["level"])
    if not users.record_sent(*claim):
        return {"queued": False, "duplicate": True, "reason": "This alert was already sent to your devices (same station, issue time, target time and level)."}
    r = OUTBOX.enqueue("[Push] " + info["subject"], "", f"push:u{owner}", station, info["level"], info["cat_rank"], info["aqi"], escalation,
                       owner=owner, claim=claim, channel="push", fields={"payload": info["push_payload"]})
    if not r.get("queued"):
        users.unrecord_sent(*claim)
    return r


def replay_alert(station, t, period="validation", profile=None, dry_run=False, escalation=False):
    """Compose and send immediately (CLI --replay-demo). The web page uses replay_enqueue() instead."""
    res, info = replay_compose(station, t, period, profile, escalation)
    if info is None:
        return res
    send(info["subject"], info["body"], info["to"], dry_run)
    return {"sent": not dry_run, "subject": info["subject"], "level": info["level"]}


def replay_enqueue(station, t, period="validation", escalation=False, profile=None, owner=None):
    """Compose and QUEUE (priority + rate limit handled by the outbox worker).
    profile/owner: a logged-in user's profile (groups, alert_from, email) and user id; None = the guest profile in data/profile.json.
    The same alert (user, station, issue time, target time, level) is never e-mailed twice, even after the replay is restarted or rewound."""
    import users
    users.init()
    prof = profile or load_profile()
    key = users.sent_key(owner, recipient(prof))
    res, info = replay_compose(station, t, period, prof, escalation)
    if info is None:
        return res
    claim = (key, "replay", station, t, info["target"], info["level"])
    if not users.record_sent(*claim):
        return {"queued": False, "duplicate": True, "reason": "This alert was already e-mailed to you (same station, issue time, target time and level)."}
    r = OUTBOX.enqueue(info["subject"], info["body"], info["to"], station, info["level"], info["cat_rank"], info["aqi"], escalation,
                       owner=owner, claim=claim)
    if not r.get("queued"):
        users.unrecord_sent(*claim)
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--replay-demo", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--station", default="silkboard")
    ap.add_argument("--time", default="2026-04-17 08:00:00")
    a = ap.parse_args()
    if a.test:
        send_test(a.dry_run)
        print("test e-mail", "composed (dry run)" if a.dry_run else "sent")
    elif a.live:
        run_live(a.dry_run)
    elif a.replay_demo:
        prof = load_profile()
        if not prof["groups"]:
            prof = {"groups": ["lung"], "station": a.station, "alert_from": 101, "email": prof["email"]}   # demo profile if none saved
        print(replay_alert(a.station, a.time, "validation", prof, a.dry_run))
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
