"""Headless test of the pages a LOGGED-IN user sees: profile, replay and live (20 Oct 2026 bug: an old cached account.js crashed the profile page with
"Could not load: Cannot set properties of null", so the form stayed empty and Log out did nothing).

Drives Chrome through the DevTools protocol (websocket-client) so that console errors and uncaught exceptions are captured, then checks:
  * no JavaScript error on profile.html, the replay page and live.html (console.error, uncaught exceptions, failed requests);
  * the saved name, age, station, health conditions and alert level appear in the profile form;
  * the header shows "Signed in as <name>", "Profile" (not on the profile page) and "Log out" on every page;
  * Log out (header link on all three pages, and the button on the profile page) ends the session and lands on the login page;
  * a missing page element (simulated) is reported but does not stop the profile from loading;
  * scripts and styles are served with Cache-Control: no-cache and the pages link versioned files (the cause of the bug).
Own fake-mode server on port 8034 with a temporary users.db (never port 8000); no e-mail can be sent.

usage (project root, aqi env):  python backend\\test_pages_logged_in.py
"""
import http.cookiejar
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import websocket

ROOT = Path(__file__).resolve().parents[1]
TMP = Path(tempfile.mkdtemp(prefix="aqi_pages_"))
PORT, DEVTOOLS = 8034, 9334
BASE = f"http://127.0.0.1:{PORT}"
CHROME = os.environ.get("CHROME_PATH") or next((p for p in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                                                             r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                                                             r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe") if Path(p).exists()), None)
USER = {"name": "Test Person", "email": "test.person@example.com", "password": "test password 1"}
PROFILE = {"age": 63, "station": "mysuru", "conditions": ["lung", "heart"], "alert_from": 51, "email_alerts": True, "replay_emails": False}
failures = []


def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  {extra}" if extra else ""))
    if not cond:
        failures.append(name)


def start_server():
    env = dict(os.environ, AQI_EMAIL_FAKE="1", AQI_USERS_DB=str(TMP / "users.db"), AQI_SECRET_KEY="pages-test-" + "q" * 40,
               AQI_RATE_FILE=str(TMP / "rate.json"), AQI_PROFILE_FILE=str(TMP / "profile.json"),
               AQI_EMAIL_STATE_FILE=str(TMP / "state.json"), AQI_EMAIL_LOG_FILE=str(TMP / "log.jsonl"))
    log = open(TMP / "server.log", "w")
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "backend.app:app", "--port", str(PORT)], cwd=ROOT, env=env, stdout=log, stderr=log)
    for _ in range(60):
        try:
            urllib.request.urlopen(BASE + "/api/meta", timeout=2)
            return proc
        except Exception:
            time.sleep(0.5)
    proc.kill()
    raise SystemExit("server did not start")


def api_session(first=False):
    """Sign up (first time) or log in through the API; returns the session cookie value."""
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

    def call(method, path, body):
        req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(), method=method, headers={"Content-Type": "application/json"})
        return json.loads(op.open(req).read())
    if first:
        call("POST", "/api/auth/signup", {**USER, "consent": True})
        call("PUT", "/api/me", PROFILE)
    else:
        call("POST", "/api/auth/login", {"email": USER["email"], "password": USER["password"]})
    return next(c.value for c in cj if c.name == "aqi_session")


class Tab:
    """Minimal DevTools-protocol client: navigate, evaluate, collect console errors / exceptions / failed requests."""

    def __init__(self, ws_url):
        self.ws = websocket.create_connection(ws_url, timeout=30, suppress_origin=True)
        self.n, self.errors = 0, []
        for m in ("Runtime.enable", "Log.enable", "Page.enable", "Network.enable"):
            self.cmd(m)

    def _event(self, msg):
        m, p = msg.get("method"), msg.get("params", {})
        if m == "Runtime.exceptionThrown":
            d = p["exceptionDetails"]
            self.errors.append("exception: " + (d.get("exception", {}).get("description") or d.get("text", "")).splitlines()[0])
        elif m == "Runtime.consoleAPICalled" and p["type"] in ("error", "assert"):
            self.errors.append("console.error: " + " ".join(str(a.get("value", a.get("description", ""))) for a in p["args"]))
        elif m == "Log.entryAdded" and p["entry"]["level"] == "error":
            self.errors.append("log: " + p["entry"]["text"] + " " + p["entry"].get("url", ""))

    def cmd(self, method, **params):
        self.n += 1
        my = self.n
        self.ws.send(json.dumps({"id": my, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == my:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})
            self._event(msg)

    def pump(self, seconds):
        end = time.time() + seconds
        self.ws.settimeout(0.2)
        while time.time() < end:
            try:
                self._event(json.loads(self.ws.recv()))
            except websocket.WebSocketTimeoutException:
                pass
        self.ws.settimeout(30)

    def js(self, expr):
        r = self.cmd("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True)
        return r.get("result", {}).get("value")

    def wait(self, expr, timeout=15):
        end = time.time() + timeout
        while time.time() < end:
            if self.js(expr):
                return True
            self.pump(0.25)
        return False

    def goto(self, url):
        self.errors = []
        self.cmd("Page.navigate", url=url)
        self.wait("document.readyState === 'complete'")

    def set_session(self, value):
        self.cmd("Network.deleteCookies", name="aqi_session", url=BASE)
        self.cmd("Network.setCookie", name="aqi_session", value=value, url=BASE, path="/", httpOnly=True, sameSite="Lax")


NAV = "(document.getElementById('acctNav') || {textContent: ''}).textContent"


def main():
    if not CHROME:
        raise SystemExit("Chrome/Edge not found; set CHROME_PATH")
    proc = start_server()
    chrome = subprocess.Popen([CHROME, "--headless=new", "--disable-gpu", "--no-sandbox", f"--remote-debugging-port={DEVTOOLS}",
                               f"--user-data-dir={TMP / 'chrome'}", "--window-size=1280,900", "about:blank"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            try:
                targets = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{DEVTOOLS}/json", timeout=2).read())
                page = next(t for t in targets if t["type"] == "page")
                break
            except Exception:
                time.sleep(0.5)
        tab = Tab(page["webSocketDebuggerUrl"])

        # ---- C. the cause: caching of page files ----
        hdr = {p: urllib.request.urlopen(BASE + p).headers.get("Cache-Control") for p in ("/account.js", "/ui.js", "/app.js", "/live.js", "/style.css", "/profile.html", "/login.html")}
        check("C1 scripts, styles and account pages are served with Cache-Control: no-cache (browser must re-check)", all(v == "no-cache" for v in hdr.values()), str(hdr))
        html = {f: (ROOT / "frontend" / f).read_text(encoding="utf-8") for f in ("index.html", "live.html", "profile.html", "login.html", "signup.html")}
        unver = {f: re.findall(r'(?:src|href)="((?:vendor/)?[a-z.]+\.(?:js|css))"', s) for f, s in html.items()}
        check("C2 every page links versioned scripts/styles (an old cached copy cannot be reused)", not any(unver.values()), str({k: v for k, v in unver.items() if v}))

        # ---- P. profile page, logged in ----
        tab.set_session(api_session(first=True))
        tab.goto(BASE + "/profile.html")
        ok = tab.wait("document.getElementById('pName').value !== ''")
        tab.pump(1.0)
        form = tab.js("""(() => ({name: pName.value, age: age.value, station: station.value, alert: alertFrom.value,
            conds: Array.from(document.querySelectorAll('input[name=cond]:checked')).map(x => x.value), emailAlerts: emailAlerts.checked,
            replay: replayEmails.checked, email: pEmail.textContent, auto: autoGroups.textContent, top: topMsg.textContent}))()""")
        check("P1 profile page: no JavaScript errors", ok and not tab.errors, str(tab.errors))
        check("P2 the saved name, age and station are in the form", form["name"] == USER["name"] and form["age"] == "63" and form["station"] == "mysuru", str(form))
        check("P3 the saved health conditions are ticked", form["conds"] == ["lung", "heart"], str(form["conds"]))
        check("P4 the saved alert level and e-mail switches are shown", form["alert"] == "51" and form["emailAlerts"] is True and form["replay"] is False, str(form))
        check("P5 age 63 shows 'Older adult' added automatically", "Older adult" in form["auto"], form["auto"])
        check("P6 no 'Could not load' message", "Could not load" not in form["top"], form["top"])
        nav = tab.js(NAV)
        check("P7 header: 'Signed in as Test Person' and 'Log out' (no 'Profile' link on the profile page itself)",
              "Signed in as Test Person" in nav and "Log out" in nav and "Profile" not in nav.replace("Signed in", ""), nav)
        check("P8a the profile page has no second, in-page Log out button and no duplicate project-name block (the top bar has both)",
              tab.js("!document.getElementById('logout') && !document.querySelector('main .auth-head')") and tab.js("!!document.getElementById('navLogout')"))
        tab.js("document.getElementById('navLogout').click()")
        out = tab.wait("location.pathname === '/login.html' && !!document.getElementById('loginForm')")
        tab.pump(0.5)
        me = tab.js("fetch('/api/me').then(r => r.status)")
        check("P8 Log out (top bar) on the profile page goes to the login page and ends the session", out and me == 401, f"(path {tab.js('location.pathname')}, /api/me {me})")

        # ---- R. replay page, logged in ----
        tab.set_session(api_session())
        tab.goto(BASE + "/")
        ok = tab.wait("document.getElementById('simTime').textContent.includes('IST') && document.getElementById('acctNav').textContent.includes('Log out')", 25)
        tab.pump(1.0)
        nav = tab.js(NAV)
        box = tab.js("document.getElementById('acctBox').hidden ? '' : document.getElementById('acctBox').textContent")
        check("R1 replay page: no JavaScript errors", ok and not tab.errors, str(tab.errors))
        check("R2 replay header: 'Signed in as Test Person', 'Profile' and 'Log out'", "Signed in as Test Person" in nav and "Profile" in nav and "Log out" in nav, nav)
        check("R3 replay uses the account profile (settings: lung, heart, older adult; alert 51; station Mysuru)",
              "Lung disease" in box and "Heart disease" in box and "Older adult" in box and "alert from AQI 51" in box and tab.js("station.value") == "mysuru", box)
        tab.js("document.getElementById('navLogout').click()")
        out = tab.wait("location.pathname === '/login.html' && !!document.getElementById('loginForm')")
        tab.pump(0.5)
        me = tab.js("fetch('/api/me').then(r => r.status)")
        tab.goto(BASE + "/")
        check("R4 the header Log out on the replay page goes to the login page; the replay page then asks for a login again",
              out and me == 401 and tab.js("location.pathname") == "/login.html", f"(/api/me {me}, after reopening / -> {tab.js('location.pathname')})")

        # ---- L. live page, logged in ----
        tab.set_session(api_session())
        tab.goto(BASE + "/live.html")
        ok = tab.wait("document.getElementById('acctNav').textContent.includes('Log out') && document.getElementById('bannerText').textContent !== 'Loading...'", 25)
        tab.pump(1.0)
        nav = tab.js(NAV)
        check("L1 live page: no JavaScript errors", ok and not tab.errors, str(tab.errors))
        check("L2 live header: 'Signed in as Test Person', 'Profile' and 'Log out'", "Signed in as Test Person" in nav and "Profile" in nav and "Log out" in nav, nav)
        tab.js("document.getElementById('navLogout').click()")
        out = tab.wait("location.pathname === '/login.html' && !!document.getElementById('loginForm')")
        tab.pump(0.5)
        check("L3 the header Log out on the live page goes to the login page and ends the session", out and tab.js("fetch('/api/me').then(r => r.status)") == 401)

        # ---- H. header Log out on the profile page, and the guard against a missing element ----
        tab.set_session(api_session())
        tab.goto(BASE + "/profile.html")
        tab.wait("document.getElementById('pName').value !== ''")
        tab.js("document.getElementById('navLogout').click()")
        check("H1 the header Log out on the profile page also goes to the login page", tab.wait("location.pathname === '/login.html'"))
        tab.set_session(api_session())
        # simulate a page that lacks an element the script uses (what an old cached script meets): remove #topMsg before account.js runs
        sid = tab.cmd("Page.addScriptToEvaluateOnNewDocument", source="new MutationObserver(() => { const e = document.getElementById('topMsg'); if (e) e.remove(); })"
                                                                       ".observe(document, {childList: true, subtree: true});")["identifier"]
        tab.goto(BASE + "/profile.html?welcome=1")
        filled = tab.wait("document.getElementById('pName').value === 'Test Person' && document.getElementById('age').value === '63'")
        tab.pump(0.8)
        exc = [e for e in tab.errors if e.startswith("exception")]
        reported = [e for e in tab.errors if "#topMsg is missing" in e]
        check("H2 a missing element is reported in the console but the form still fills and nothing crashes", filled and not exc and reported, str(tab.errors))
        tab.cmd("Page.removeScriptToEvaluateOnNewDocument", identifier=sid)
        tab.js("document.getElementById('navLogout').click()")
        check("H3 Log out still works on that page", tab.wait("location.pathname === '/login.html'"))
        tab.ws.close()
    finally:
        chrome.kill()
        proc.kill()
    print()
    print("ALL PASSED" if not failures else f"{len(failures)} FAILED: {failures}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
