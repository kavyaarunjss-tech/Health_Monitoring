"""Account endpoints: sign-up, login, logout, own profile, delete account, e-mail verification and password reset (see users.py).

Every /api/me endpoint works on the user of the session cookie only; no endpoint accepts a user id, so nobody can read or change
another user's data. Changing requests must come from this site (Origin check) and the cookie is SameSite=Lax + HttpOnly.
"""
import json
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

import notify_email as ne
import notify_push as npu
import notify_twilio as ntw
import users

COOKIE = "aqi_session"
router = APIRouter()
users.init()

_link_sent = {}                 # (user id, kind) -> real time of the last link e-mail (resend limit)
LINK_GAP_S = {"verify": 120, "reset": 300}


def same_origin(request: Request):
    """Reject changing requests sent from another web site (defence in depth next to SameSite cookies)."""
    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") != str(request.base_url).rstrip("/"):
        raise HTTPException(403, "Request from another site refused.")


def current_user(request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    row = users.session_user(request.cookies.get(COOKIE))
    if row is None:
        raise HTTPException(401, "Not logged in.")
    return row


def optional_user(request: Request):
    """The logged-in user row, or None for a guest (used by the replay e-mail endpoint)."""
    return users.session_user(request.cookies.get(COOKIE))


def set_cookie(request, response, token):
    response.set_cookie(COOKIE, token, max_age=users.SESSION_DAYS * 86400, httponly=True, samesite="lax",
                        secure=request.url.scheme == "https", path="/")


def fail(e: users.AuthError):
    raise HTTPException(e.status, str(e))


def send_link(request, user_row, kind):
    """E-mail a one-time link in the background (SMTP takes seconds). Returns False if e-mail is not configured or sent too recently."""
    if not ne.configured():
        return False
    key = (user_row["id"], kind)
    if time.time() - _link_sent.get(key, 0) < LINK_GAP_S[kind]:
        return False
    _link_sent[key] = time.time()
    token = users.new_link_token(user_row["id"], kind)
    page = "api/auth/verify?token=" if kind == "verify" else "reset.html?token="
    link = str(request.base_url) + page + token

    def go():
        try:
            ne.send_account_link(kind, user_row["email"], user_row["name"], link)
        except Exception as e:      # never log the link or credentials
            print(f"account e-mail ({kind}) failed: {type(e).__name__}")
    threading.Thread(target=go, daemon=True).start()
    return True


class SignupIn(BaseModel):
    name: str
    email: str
    password: str
    consent: bool = False


class LoginIn(BaseModel):
    email: str
    password: str


class ProfileIn(BaseModel):
    name: str | None = None
    age: int | None = None
    station: str | None = None
    conditions: list[str] | None = None
    alert_from: int | None = None          # None = default for the profile
    email_alerts: bool | None = None
    replay_emails: bool | None = None
    whatsapp: str | None = None             # E.164, e.g. +919876543210 ("" = remove)
    whatsapp_alerts: bool | None = None
    replay_whatsapp: bool | None = None


class TestWaIn(BaseModel):
    whatsapp: str | None = None             # the number typed on the page (may not be saved yet); default = the saved number


class PasswordIn(BaseModel):
    password: str


class ForgotIn(BaseModel):
    email: str


class ResetIn(BaseModel):
    token: str
    password: str


@router.get("/api/account/options")
def options():
    return {"conditions": users.CONDITIONS, "stations": users.STATIONS, "alert_choices": users.ALERT_CHOICES,
            "child_under": users.CHILD_UNDER, "older_from": users.OLDER_FROM, "min_password": users.MIN_PASSWORD,
            "email_configured": ne.configured(), "whatsapp_configured": ntw.configured(),
            "wa_sandbox": {"number": ntw.SANDBOX_NUMBER, "join": ntw.SANDBOX_JOIN}}


@router.post("/api/auth/signup", dependencies=[Depends(same_origin)])
def signup(body: SignupIn, request: Request, response: Response):
    try:
        uid = users.signup(body.name, body.email, body.password, body.consent)
    except users.AuthError as e:
        fail(e)
    set_cookie(request, response, users.new_session(uid))
    row = users.get(uid)
    sent = send_link(request, row, "verify")
    return {**users.public(row), "verification_sent": sent}


@router.post("/api/auth/login", dependencies=[Depends(same_origin)])
def login(body: LoginIn, request: Request, response: Response):
    try:
        uid = users.login(body.email, body.password)
    except users.AuthError as e:
        fail(e)
    set_cookie(request, response, users.new_session(uid))
    return users.public(users.get(uid))


@router.post("/api/auth/logout", dependencies=[Depends(same_origin)])
def logout(request: Request, response: Response):
    users.end_session(request.cookies.get(COOKIE))
    response.delete_cookie(COOKIE, path="/")
    response.delete_cookie("aqi_guest", path="/")         # after logging out the login page is shown again
    return {"ok": True}


@router.get("/api/auth/session")
def session(request: Request, response: Response):
    """Who is logged in, for the page header: always 200 (a guest gets {"user": null}), so pages can ask without logging a 401 in the
    browser console. /api/me (401 when logged out) is unchanged."""
    response.headers["Cache-Control"] = "no-store"
    row = users.session_user(request.cookies.get(COOKIE))
    return {"user": None if row is None else {**users.public(row), "email_configured": ne.configured(), "whatsapp_configured": ntw.configured()}}


@router.get("/api/me")
def me(user=Depends(current_user)):
    return {**users.public(user), "email_configured": ne.configured(), "whatsapp_configured": ntw.configured()}


@router.put("/api/me", dependencies=[Depends(same_origin)])
def update_me(body: ProfileIn, request: Request, user=Depends(current_user)):
    data = body.model_dump(exclude_unset=True)
    if "alert_from" in data and data["alert_from"] is None:
        data["alert_from"] = "default"
    try:
        return {**users.update_profile(user["id"], data), "email_configured": ne.configured(), "whatsapp_configured": ntw.configured()}
    except users.AuthError as e:
        fail(e)


@router.post("/api/me/delete", dependencies=[Depends(same_origin)])
def delete_me(body: PasswordIn, request: Request, response: Response, user=Depends(current_user)):
    """Delete the account and all its data. Needs the password again (so an open browser alone cannot delete it)."""
    try:
        users.login(user["email"], body.password)
    except users.AuthError as e:
        fail(users.AuthError(e.status, "Wrong password: account not deleted." if e.status == 401 else str(e)))
    email = users.delete_user(user["id"])
    ne.forget_user(user["id"], email)
    response.delete_cookie(COOKIE, path="/")
    return {"deleted": True}


@router.post("/api/me/test-whatsapp", dependencies=[Depends(same_origin)])
def test_whatsapp(body: TestWaIn, user=Depends(current_user)):
    """Send one test WhatsApp message to the user's number (rate-limited like every WhatsApp message). Twilio reports problems such as
    'not joined' (63015) or 'outside 24 h' (63016) a few seconds later; the final result is stored and shown on the profile page."""
    try:
        number = users.clean_whatsapp(body.whatsapp if body.whatsapp is not None else user["whatsapp"])
    except users.AuthError as e:
        fail(e)
    if not number:
        raise HTTPException(400, "Add your WhatsApp number first.")
    if not ntw.configured():
        raise HTTPException(503, "WhatsApp is not configured on this computer (.env needs TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_FROM).")
    try:
        ntw.reserve_slot()
    except ntw.RateLimited as e:
        raise HTTPException(429, f"{e}. Try again in {int(e.retry_after) + 1} s.", headers={"Retry-After": str(int(e.retry_after) + 1)})
    uid = user["id"]
    text = ("Test message from the Integrated Air Quality & Health Risk Prediction Framework (student research prototype). "
            "If you can read this, WhatsApp alerts reach this phone.")
    test_fields = {"station": "TEST message", "aqi": "no real forecast", "time": "now", "level": "Test",
                   "advice": "If you can read this, WhatsApp alerts reach this phone."}
    res = ntw.send_whatsapp(number, text, on_result=lambda ok, code, why: users.set_wa_status(uid, ok, code, why, kind="test"), kind="test",
                            fields=test_fields)
    if not res["ok"]:
        return {"sent": False, "code": res["code"], "reason": res["reason"]}
    return {"sent": True, "check_after_s": ntw.CHECK_AFTER_S,
            "reason": "Accepted by Twilio. Delivery is checked in a few seconds; the result appears below."}


# ---------------------------------------------------------------- Web Push ("Alerts on this phone"), added 26 Oct 2026
class PushKeysIn(BaseModel):
    p256dh: str
    auth: str


class PushSubIn(BaseModel):
    endpoint: str
    keys: PushKeysIn


class PushSaveIn(BaseModel):
    subscription: PushSubIn
    live: bool = False
    replay: bool = False


class PushEndpointIn(BaseModel):
    endpoint: str


@router.get("/api/push/key")
def push_key():
    """The VAPID public key the browser needs to subscribe (public by design). configured=False when .env has no VAPID keys."""
    ok = npu.configured()
    return {"configured": ok, "key": npu.public_key() if ok else None}


@router.post("/api/me/push/subscribe", dependencies=[Depends(same_origin)])
def push_subscribe(body: PushSaveIn, user=Depends(current_user)):
    """Store THIS device's subscription with its switches (live alerts / replay-demo alerts). Both off = remove the device."""
    if not body.live and not body.replay:
        users.delete_push_sub(body.subscription.endpoint, user["id"])
        return {"saved": False, "removed": True}
    try:
        users.save_push_sub(user["id"], body.subscription.endpoint, body.subscription.keys.p256dh, body.subscription.keys.auth, body.live, body.replay)
    except ValueError:
        raise HTTPException(400, "This does not look like a browser push subscription.")
    return {"saved": True, "live": body.live, "replay": body.replay}


@router.post("/api/me/push/unsubscribe", dependencies=[Depends(same_origin)])
def push_unsubscribe(body: PushEndpointIn, user=Depends(current_user)):
    users.delete_push_sub(body.endpoint, user["id"])
    return {"removed": True}


@router.post("/api/me/push/status", dependencies=[Depends(same_origin)])
def push_status(body: PushEndpointIn, user=Depends(current_user)):
    """Switches and last result of THIS device (the endpoint is sent in the body, never in a URL that could be logged)."""
    s = users.push_sub(user["id"], body.endpoint)
    return {"subscribed": bool(s), "live": bool(s and s["live"]), "replay": bool(s and s["replay"]),
            "last": json.loads(s["last"]) if s and s["last"] else None, "devices": len(users.push_subs(user["id"]))}


@router.post("/api/me/push/test", dependencies=[Depends(same_origin)])
def push_test(body: PushEndpointIn, user=Depends(current_user)):
    """Send one test notification to THIS device (rate-limited like every push)."""
    s = users.push_sub(user["id"], body.endpoint)
    if not s:
        raise HTTPException(400, "Turn on 'Alerts on this phone' first.")
    if not npu.configured() and not npu.FAKE:
        raise HTTPException(503, "Push notifications are not configured on this computer (.env needs VAPID keys: run python backend\\make_vapid_keys.py).")
    try:
        npu.reserve_slot()
    except npu.RateLimited as e:
        raise HTTPException(429, f"{e}. Try again in {int(e.retry_after) + 1} s.", headers={"Retry-After": str(int(e.retry_after) + 1)})
    res = npu.send_push(s, npu.test_payload(), "test")
    if res["removed"]:
        return {"sent": False, "removed": True, "reason": "The browser's push service says this subscription has expired; turn the switch on again."}
    return {"sent": res["ok"], "status": res["status"],
            "reason": "Sent: the notification should appear in a few seconds." if res["ok"] else f"The push service refused it ({res['status']})."}


@router.post("/api/me/send-verification", dependencies=[Depends(same_origin)])
def resend_verification(request: Request, user=Depends(current_user)):
    if user["email_verified"]:
        return {"sent": False, "reason": "Your e-mail address is already confirmed."}
    if not ne.configured():
        return {"sent": False, "reason": "E-mail sending is not configured on this computer (.env)."}
    ok = send_link(request, user, "verify")
    return {"sent": ok, "reason": "" if ok else f"A link was sent less than {LINK_GAP_S['verify'] // 60} minutes ago; please check your inbox."}


@router.get("/api/auth/verify")
def verify(token: str = ""):
    uid = users.use_link_token(token, "verify")
    return RedirectResponse("/profile.html?verified=" + ("1" if uid else "0"), status_code=303)


@router.post("/api/auth/forgot", dependencies=[Depends(same_origin)])
def forgot(body: ForgotIn, request: Request):
    """Always the same answer, so the page does not reveal which e-mail addresses have accounts."""
    uid = users.user_id_by_email(body.email)
    if uid is not None:
        send_link(request, users.get(uid), "reset")
    return {"ok": True, "email_configured": ne.configured(),
            "message": "If an account exists for this address, a reset link has been e-mailed. It works once and expires in 1 hour."}


@router.post("/api/auth/reset", dependencies=[Depends(same_origin)])
def reset(body: ResetIn):
    try:
        users.check_password(body.password)
    except users.AuthError as e:
        fail(e)
    uid = users.use_link_token(body.token, "reset")
    if uid is None:
        raise HTTPException(400, "This reset link is invalid, already used or expired. Please ask for a new one.")
    users.set_password(uid, body.password, verified=True)
    return {"ok": True}
