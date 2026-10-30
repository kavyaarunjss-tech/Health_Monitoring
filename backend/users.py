"""User accounts: sign-up, login sessions, profiles (SQLite data/users.db, git-ignored; path override AQI_USERS_DB for tests).

Security rules
  * Passwords are hashed with Argon2id (argon2-cffi); the plain password is never stored or logged. Minimum 8 characters.
  * A session is a random 256-bit token in an HTTP-only cookie. The database keeps only HMAC-SHA256(secret key, token), so a copy of
    users.db cannot be used to log in. The secret key comes from AQI_SECRET_KEY (environment or .env, never in code or git); if it is
    missing, one is generated once and appended to .env.
  * E-mail verification and password-reset links use one-time tokens stored the same (hashed) way; they expire (24 h / 1 h).
  * Nothing here takes a user id from the request: every profile read/write uses the user of the session cookie.

Profile rules
  * Health conditions the user ticks: lung, heart, pregnant, outdoor_worker, athlete.
  * Age < 14 adds "child" automatically ([4] in docs/health_advisory_reference.md); age >= 60 adds "older" (a DESIGN CHOICE: the reference
    gives no age for "older adult").
  * Alert level: None = the default for the profile (vulnerable 101, healthy 201); a stored number may only be LOWER than the default.
"""
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

import advice as adv

ROOT = Path(__file__).resolve().parents[1]
DB = Path(os.environ.get("AQI_USERS_DB", ROOT / "data" / "users.db"))
SESSION_DAYS = 14
MIN_PASSWORD = 8
CONDITIONS = ["lung", "heart", "pregnant", "outdoor_worker", "athlete"]        # ticked by the user
CHILD_UNDER, OLDER_FROM = 14, 60                                               # age rules (60 is a design choice)
ALERT_CHOICES = [51, 101, 151, 201, 301]
STATIONS = ["silkboard", "hebbal", "jayanagar", "chikkaballapura", "chikkamagaluru", "mysuru", "ramanagara", "madikeri"]
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_ph = PasswordHasher()                       # Argon2id with the library's recommended parameters
_DUMMY_HASH = _ph.hash("not-a-real-password")  # login with an unknown e-mail still does one hash check (same timing)
_lock = threading.Lock()


class AuthError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


# ---------------------------------------------------------------- secret key
_secret = None


def secret_key():
    global _secret
    if _secret:
        return _secret
    key = os.environ.get("AQI_SECRET_KEY")
    envf = ROOT / ".env"
    if not key and envf.exists():
        for line in envf.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("AQI_SECRET_KEY="):
                key = line.split("=", 1)[1].strip().strip('"')
    if not key:
        key = secrets.token_urlsafe(48)
        with open(envf, "a", encoding="utf-8") as fh:            # .env is git-ignored
            fh.write(("\n" if envf.exists() and not envf.read_text(encoding="utf-8").endswith("\n") else "") + f"AQI_SECRET_KEY={key}\n")
        print("users: generated a new AQI_SECRET_KEY and added it to .env")
    _secret = key.encode("utf-8")
    return _secret


def token_hash(token):
    return hmac.new(secret_key(), token.encode("utf-8"), hashlib.sha256).hexdigest()


# ---------------------------------------------------------------- database
def con():
    DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    return c


def init():
    with _lock, con() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,              -- stored lower-case
            pw_hash TEXT NOT NULL,                   -- Argon2id hash, never the password
            email_verified INTEGER NOT NULL DEFAULT 0,
            age INTEGER,
            station TEXT NOT NULL DEFAULT 'silkboard',
            conditions TEXT NOT NULL DEFAULT '[]',   -- JSON list from CONDITIONS
            alert_from INTEGER,                      -- NULL = default for the profile; otherwise <= default
            email_alerts INTEGER NOT NULL DEFAULT 0,
            replay_emails INTEGER NOT NULL DEFAULT 0,
            consent_at TEXT NOT NULL,
            created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions (
            token_hash TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sent_alerts (     -- every alert e-mail ever queued/sent, so the same alert is never e-mailed twice
            user_key TEXT NOT NULL,                  -- 'u<id>' for an account, 'guest:<address>' for the guest profile
            mode TEXT NOT NULL,                      -- 'replay' or 'live'
            station TEXT NOT NULL,
            issued TEXT NOT NULL,                    -- forecast issue time (replay: simulated hour; live: newest observation)
            target TEXT NOT NULL,                    -- target hour (hour ending)
            level TEXT NOT NULL,                     -- 'likely' or 'possible'
            sent_at TEXT NOT NULL,
            PRIMARY KEY (user_key, mode, station, issued, target, level));
        CREATE TABLE IF NOT EXISTS push_subs (       -- Web Push subscriptions (one per browser / phone), added 26 Oct 2026
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            endpoint TEXT NOT NULL UNIQUE,           -- the push service URL of this device (a secret capability: never logged)
            p256dh TEXT NOT NULL,                    -- the device's public key and auth secret (needed to encrypt; never logged)
            auth TEXT NOT NULL,
            live INTEGER NOT NULL DEFAULT 0,         -- live alerts on this device
            replay INTEGER NOT NULL DEFAULT 0,       -- replay-demo alerts on this device
            created_at TEXT NOT NULL,
            last TEXT);                              -- JSON: last delivery result (time, ok, status, kind)
        CREATE TABLE IF NOT EXISTS tokens (          -- one-time e-mail verification / password reset links
            token_hash TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            purpose TEXT NOT NULL,                   -- 'verify' or 'reset'
            expires_at TEXT NOT NULL);
        """)
        # WhatsApp channel (added 24 Oct 2026): new columns are added to an existing users.db automatically
        have = {r[1] for r in c.execute("PRAGMA table_info(users)")}
        for col, decl in (("whatsapp", "TEXT"),                                   # E.164 number, e.g. +919876543210
                          ("whatsapp_alerts", "INTEGER NOT NULL DEFAULT 0"),      # live alerts by WhatsApp
                          ("replay_whatsapp", "INTEGER NOT NULL DEFAULT 0"),      # replay-demo alerts by WhatsApp
                          ("wa_last", "TEXT")):                                   # JSON: last WhatsApp delivery result
            if col not in have:
                c.execute(f"ALTER TABLE users ADD COLUMN {col} {decl}")


def now_s():
    return datetime.now().isoformat(timespec="seconds")


# ---------------------------------------------------------------- profile rules
def derived_groups(age, conditions):
    groups = [c for c in CONDITIONS if c in (conditions or [])]
    if age is not None and age < CHILD_UNDER:
        groups.append("child")
    if age is not None and age >= OLDER_FROM:
        groups.append("older")
    return groups


def default_alert(groups):
    return adv.DEFAULT_ALERT["vulnerable" if set(groups) & adv.VULNERABLE_GROUPS else "healthy"]


def public(row):
    """The profile as the owner sees it (no password hash, no internal fields)."""
    conds = json.loads(row["conditions"] or "[]")
    groups = derived_groups(row["age"], conds)
    dflt = default_alert(groups)
    eff = dflt if row["alert_from"] is None else min(row["alert_from"], dflt)
    auto = (["child"] if row["age"] is not None and row["age"] < CHILD_UNDER else []) + (["older"] if row["age"] is not None and row["age"] >= OLDER_FROM else [])
    return {"name": row["name"], "email": row["email"], "email_verified": bool(row["email_verified"]), "age": row["age"],
            "station": row["station"], "conditions": conds, "auto_groups": auto, "groups": groups,
            "alert_from": row["alert_from"], "alert_default": dflt, "alert_effective": eff,
            "alert_choices": [v for v in ALERT_CHOICES if v <= dflt],
            "email_alerts": bool(row["email_alerts"]), "replay_emails": bool(row["replay_emails"]), "created_at": row["created_at"],
            "whatsapp": row["whatsapp"] or "", "whatsapp_alerts": bool(row["whatsapp_alerts"]), "replay_whatsapp": bool(row["replay_whatsapp"]),
            "wa_last": json.loads(row["wa_last"]) if row["wa_last"] else None}


E164 = re.compile(r"^\+[1-9]\d{7,14}$")


def clean_whatsapp(number):
    """'' / None -> None (no number); otherwise an E.164 number like +919876543210 (spaces, dashes and brackets are removed)."""
    n = re.sub(r"[\s\-().]", "", str(number or ""))
    if not n:
        return None
    if not E164.match(n):
        raise AuthError(400, "WhatsApp number must be in international format with the country code, e.g. +919876543210.")
    return n


def clean_name(name):
    name = " ".join(str(name or "").split())
    if not 1 <= len(name) <= 80:
        raise AuthError(400, "Please enter your name (up to 80 characters).")
    return name


def clean_email(email):
    email = str(email or "").strip().lower()
    if len(email) > 254 or not EMAIL_RE.match(email):
        raise AuthError(400, "Please enter a valid e-mail address.")
    return email


def check_password(pw):
    if not isinstance(pw, str) or len(pw) < MIN_PASSWORD:
        raise AuthError(400, f"The password must have at least {MIN_PASSWORD} characters.")
    if len(pw) > 256:
        raise AuthError(400, "The password is too long (max 256 characters).")


def clean_age(age):
    if age in (None, ""):
        return None
    try:
        a = int(age)
    except (TypeError, ValueError):
        raise AuthError(400, "Age must be a whole number.")
    if not 0 <= a <= 120:
        raise AuthError(400, "Age must be between 0 and 120.")
    return a


# ---------------------------------------------------------------- sign-up / login / sessions
def signup(name, email, password, consent):
    if consent is not True:
        raise AuthError(400, "Please tick the consent box to create an account.")
    name, email = clean_name(name), clean_email(email)
    check_password(password)
    pw_hash = _ph.hash(password)
    try:
        with _lock, con() as c:
            cur = c.execute("INSERT INTO users (name, email, pw_hash, consent_at, created_at) VALUES (?,?,?,?,?)",
                            (name, email, pw_hash, now_s(), now_s()))
            return cur.lastrowid
    except sqlite3.IntegrityError:
        raise AuthError(409, "An account with this e-mail already exists. Please log in.")


# failed-login limiter: at most 5 wrong passwords per e-mail in 15 minutes (in memory)
_fails = {}
FAIL_MAX, FAIL_WINDOW_S = 5, 900


def login(email, password):
    email = str(email or "").strip().lower()
    t = time.time()
    with _lock:
        recent = [x for x in _fails.get(email, []) if t - x < FAIL_WINDOW_S]
        _fails[email] = recent
    if len(recent) >= FAIL_MAX:
        raise AuthError(429, "Too many wrong passwords. Please wait 15 minutes or reset your password.")
    with con() as c:
        row = c.execute("SELECT id, pw_hash FROM users WHERE email=?", (email,)).fetchone()
    ok = False
    try:
        ok = _ph.verify(row["pw_hash"] if row else _DUMMY_HASH, str(password or "")) and row is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        ok = False
    if not ok:
        with _lock:
            _fails.setdefault(email, []).append(t)
        raise AuthError(401, "Wrong e-mail or password.")
    with _lock:
        _fails.pop(email, None)
    if _ph.check_needs_rehash(row["pw_hash"]):
        with con() as c:
            c.execute("UPDATE users SET pw_hash=? WHERE id=?", (_ph.hash(password), row["id"]))
    return row["id"]


def new_session(user_id):
    token = secrets.token_urlsafe(32)
    with _lock, con() as c:
        c.execute("DELETE FROM sessions WHERE expires_at < ?", (now_s(),))
        c.execute("INSERT INTO sessions VALUES (?,?,?,?)", (token_hash(token), user_id, now_s(),
                                                            (datetime.now() + timedelta(days=SESSION_DAYS)).isoformat(timespec="seconds")))
    return token


def session_user(token):
    """The user row of a valid session token, or None."""
    if not token or len(token) > 200:
        return None
    with con() as c:
        return c.execute("SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token_hash=? AND s.expires_at >= ?",
                         (token_hash(token), now_s())).fetchone()


def end_session(token):
    if token:
        with _lock, con() as c:
            c.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash(token),))


# ---------------------------------------------------------------- profile
def get(user_id):
    with con() as c:
        return c.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()


def update_profile(user_id, data):
    """Validate and store the editable fields. The alert level is capped at the default of the NEW profile (may lower, never raise)."""
    row = get(user_id)
    if row is None:
        raise AuthError(401, "Not logged in.")
    name = clean_name(data.get("name", row["name"]))
    age = clean_age(data["age"]) if "age" in data else row["age"]
    station = data.get("station", row["station"])
    if station not in STATIONS:
        raise AuthError(400, "Unknown station.")
    conds = data.get("conditions", json.loads(row["conditions"]))
    if not isinstance(conds, list) or any(c not in CONDITIONS for c in conds):
        raise AuthError(400, "Unknown health condition.")
    conds = [c for c in CONDITIONS if c in conds]
    dflt = default_alert(derived_groups(age, conds))
    alert = data.get("alert_from", row["alert_from"])
    if alert in (None, "", "default"):
        alert = None
    else:
        try:
            alert = int(alert)
        except (TypeError, ValueError):
            raise AuthError(400, "Alert level must be a number.")
        alert = None if alert >= dflt else max(1, alert)          # at or above the default -> the default (never higher)
    email_alerts = bool(data.get("email_alerts", row["email_alerts"]))
    replay_emails = bool(data.get("replay_emails", row["replay_emails"]))
    whatsapp = clean_whatsapp(data["whatsapp"]) if "whatsapp" in data else row["whatsapp"]
    wa_alerts = bool(data.get("whatsapp_alerts", row["whatsapp_alerts"]))
    wa_replay = bool(data.get("replay_whatsapp", row["replay_whatsapp"]))
    if (wa_alerts or wa_replay) and not whatsapp:
        raise AuthError(400, "Add your WhatsApp number to receive alerts by WhatsApp.")
    with _lock, con() as c:
        c.execute("UPDATE users SET name=?, age=?, station=?, conditions=?, alert_from=?, email_alerts=?, replay_emails=?, whatsapp=?, "
                  "whatsapp_alerts=?, replay_whatsapp=? WHERE id=?",
                  (name, age, station, json.dumps(conds), alert, int(email_alerts), int(replay_emails), whatsapp, int(wa_alerts), int(wa_replay),
                   user_id))
    return public(get(user_id))


def set_wa_status(user_id, ok, code=None, reason="", kind="alert"):
    """Remember the last WhatsApp delivery result (shown on the profile page). Never contains credentials."""
    if user_id is None:
        return
    with _lock, con() as c:
        c.execute("UPDATE users SET wa_last=? WHERE id=?",
                  (json.dumps({"time": now_s(), "ok": bool(ok), "code": code, "reason": reason, "kind": kind}), user_id))


def delete_user(user_id):
    """Delete the account and everything stored for it (sessions and tokens go by ON DELETE CASCADE; the sent-alert record by key).
    Returns the e-mail address."""
    row = get(user_id)
    with _lock, con() as c:
        c.execute("DELETE FROM users WHERE id=?", (user_id,))
        c.execute("DELETE FROM sent_alerts WHERE user_key=?", (f"u{user_id}",))
    return row["email"] if row else None


def set_password(user_id, password, verified=False):
    """verified=True after a reset link: using the e-mailed link proves the address belongs to the user."""
    check_password(password)
    with _lock, con() as c:
        c.execute("UPDATE users SET pw_hash=?, email_verified=MAX(email_verified, ?) WHERE id=?", (_ph.hash(password), int(verified), user_id))
        c.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))         # log out everywhere after a password change


# ---------------------------------------------------------------- one-time links (verify e-mail, reset password)
TOKEN_LIFE = {"verify": timedelta(hours=24), "reset": timedelta(hours=1)}


def new_link_token(user_id, purpose):
    token = secrets.token_urlsafe(32)
    with _lock, con() as c:
        c.execute("DELETE FROM tokens WHERE user_id=? AND purpose=?", (user_id, purpose))      # only the newest link works
        c.execute("INSERT INTO tokens VALUES (?,?,?,?)", (token_hash(token), user_id, purpose,
                                                          (datetime.now() + TOKEN_LIFE[purpose]).isoformat(timespec="seconds")))
    return token


def use_link_token(token, purpose):
    """Consume a one-time token; returns the user id or None (unknown, expired or already used)."""
    if not token or len(token) > 200:
        return None
    with _lock, con() as c:
        row = c.execute("SELECT user_id, expires_at FROM tokens WHERE token_hash=? AND purpose=?", (token_hash(token), purpose)).fetchone()
        if row is None:
            return None
        c.execute("DELETE FROM tokens WHERE token_hash=?", (token_hash(token),))
        if row["expires_at"] < now_s():
            return None
        if purpose == "verify":
            c.execute("UPDATE users SET email_verified=1 WHERE id=?", (row["user_id"],))
        return row["user_id"]


def user_id_by_email(email):
    with con() as c:
        r = c.execute("SELECT id FROM users WHERE email=?", (str(email or "").strip().lower(),)).fetchone()
    return r["id"] if r else None


def alert_users():
    """Users who want LIVE alerts on at least one channel: e-mail (needs a confirmed address), WhatsApp (needs a number) and/or push (a device
    with live alerts on). Each entry: id, email, name, whatsapp, the channel switches "email_on" / "wa_on" / "push_on", and the profile dict."""
    with con() as c:
        rows = c.execute("SELECT * FROM users WHERE (email_alerts=1 AND email_verified=1) OR (whatsapp_alerts=1 AND whatsapp IS NOT NULL "
                         "AND whatsapp != '') OR id IN (SELECT user_id FROM push_subs WHERE live=1) ORDER BY id").fetchall()
        live_push = {r[0] for r in c.execute("SELECT DISTINCT user_id FROM push_subs WHERE live=1")}
    out = []
    for r in rows:
        p = public(r)
        out.append({"id": r["id"], "email": r["email"], "name": r["name"], "whatsapp": r["whatsapp"] or "",
                    "email_on": bool(r["email_alerts"] and r["email_verified"]), "wa_on": bool(r["whatsapp_alerts"] and r["whatsapp"]),
                    "push_on": r["id"] in live_push,
                    "profile": {"groups": p["groups"], "station": p["station"], "alert_from": p["alert_effective"], "email": r["email"]}})
    return out


# ---------------------------------------------------------------- Web Push subscriptions (per device)
PUSH_ENDPOINT_RE = re.compile(r"^https://[A-Za-z0-9.-]+(:\d+)?/[^\s]{8,1500}$")


def save_push_sub(user_id, endpoint, p256dh, auth, live, replay):
    """Store (or update) this device's subscription for this user. A device belongs to one account: subscribing again from another
    account moves it."""
    if not PUSH_ENDPOINT_RE.match(endpoint or "") or not p256dh or not auth or len(p256dh) > 200 or len(auth) > 100:
        raise ValueError("invalid push subscription")
    with _lock, con() as c:
        c.execute("INSERT INTO push_subs (user_id, endpoint, p256dh, auth, live, replay, created_at) VALUES (?,?,?,?,?,?,?) "
                  "ON CONFLICT(endpoint) DO UPDATE SET user_id=excluded.user_id, p256dh=excluded.p256dh, auth=excluded.auth, "
                  "live=excluded.live, replay=excluded.replay", (user_id, endpoint, p256dh, auth, int(bool(live)), int(bool(replay)), now_s()))


def push_subs(user_id, mode=None):
    """This user's devices; mode 'live' / 'replay' = only the devices with that switch on."""
    q = "SELECT * FROM push_subs WHERE user_id=?" + {"live": " AND live=1", "replay": " AND replay=1"}.get(mode, "") + " ORDER BY id"
    with con() as c:
        return [dict(r) for r in c.execute(q, (user_id,)).fetchall()]


def push_sub(user_id, endpoint):
    with con() as c:
        r = c.execute("SELECT * FROM push_subs WHERE user_id=? AND endpoint=?", (user_id, endpoint)).fetchone()
    return dict(r) if r else None


def delete_push_sub(endpoint, user_id=None):
    with _lock, con() as c:
        if user_id is None:
            c.execute("DELETE FROM push_subs WHERE endpoint=?", (endpoint,))
        else:
            c.execute("DELETE FROM push_subs WHERE endpoint=? AND user_id=?", (endpoint, user_id))


def set_push_status(sub_id, ok, status, kind):
    with _lock, con() as c:
        c.execute("UPDATE push_subs SET last=? WHERE id=?", (json.dumps({"time": now_s(), "ok": bool(ok), "status": status, "kind": kind}), sub_id))


# ---------------------------------------------------------------- "already sent" record (no duplicate alert e-mails)
def sent_key(owner, address):
    return f"u{owner}" if owner is not None else f"guest:{str(address or '').lower()}"


def record_sent(key, mode, station, issued, target, level):
    """Atomically claim an alert e-mail. True = new (go ahead and send); False = this exact alert was already e-mailed to this user."""
    with _lock, con() as c:
        cur = c.execute("INSERT OR IGNORE INTO sent_alerts VALUES (?,?,?,?,?,?,?)", (key, mode, station, issued, target, level, now_s()))
        return cur.rowcount == 1


def unrecord_sent(key, mode, station, issued, target, level):
    """Release a claim when the e-mail was not queued or the send failed (so it may be sent later)."""
    with _lock, con() as c:
        c.execute("DELETE FROM sent_alerts WHERE user_key=? AND mode=? AND station=? AND issued=? AND target=? AND level=?",
                  (key, mode, station, issued, target, level))


def count_sent(key):
    with con() as c:
        return c.execute("SELECT COUNT(*) FROM sent_alerts WHERE user_key=?", (key,)).fetchone()[0]
