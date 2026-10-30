"""Headless test of the personalised alert pop-up and the page switch (replay page, logged in). Saves screenshots to screenshots_preview/.

Two accounts with different profiles (A: lung disease, B: child, age 8) look at the same replay hour (Silk Board, 24 Apr 2026 01:00, forecast Poor):
  * each gets an alert pop-up with at most 5 lines (forecast line + up to 4 personal lines), every personal line with a citation;
  * the pop-ups of A and B differ (their own health-group line);
  * two consecutive alerts for A read differently (rotating tip);
  * no JavaScript errors; the "Replay demo | Live data" switch highlights the current page on both pages; Profile and Log out are buttons.
Own fake-mode server on port 8035 (DevTools 9335), temporary users.db; never port 8000; no e-mail (replay e-mails off, fake mode).

usage (project root, aqi env):  python backend\\test_popup_advice.py
"""
import base64
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_pages_logged_in as T  # noqa: E402  (server start, DevTools client)

T.PORT, T.DEVTOOLS = 8035, 9335
T.BASE = f"http://127.0.0.1:{T.PORT}"
BASE = T.BASE
OUT = T.ROOT / "screenshots_preview"
HOUR, HOUR2 = "2026-04-24 01:00:00", "2026-04-24 06:00:00"
failures = T.failures
check = T.check


def account(name, email, profile):
    import http.cookiejar
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

    def call(method, path, body):
        req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(), method=method, headers={"Content-Type": "application/json"})
        return json.loads(op.open(req).read())
    call("POST", "/api/auth/signup", {"name": name, "email": email, "password": "test password 1", "consent": True})
    call("PUT", "/api/me", profile)
    return next(c.value for c in cj if c.name == "aqi_session")


def shot(tab, name):
    data = tab.cmd("Page.captureScreenshot", format="png")["data"]
    (OUT / name).write_bytes(base64.b64decode(data))


def popup_at(tab, hour, reset=True):
    """Move the replay to `hour` like a user stepping there, and return the pop-up content."""
    tab.js("""(async () => { stop(); %s S.idx = S.hours.indexOf(%s); await show(); return true; })()""" %
           ("S.lastIssued = {}; clearAlert('profile');" if reset else "", json.dumps(hour)))
    tab.wait("!!document.querySelector('#toasts .toast')", 10)
    tab.pump(0.4)
    return tab.js("""(() => { const t = document.querySelector('#toasts .toast'); if (!t) return null;
        const lis = Array.from(t.querySelectorAll('.toast-lines li'));
        return { title: t.querySelector('b').textContent, body: t.querySelector('.small:not(.muted)').textContent,
                 lines: lis.map(li => li.textContent), sources: lis.map(li => (li.querySelector('.src') || {}).textContent || '') }; })()""")


def main():
    proc = T.start_server()
    chrome = subprocess.Popen([T.CHROME, "--headless=new", "--disable-gpu", "--no-sandbox", f"--remote-debugging-port={T.DEVTOOLS}",
                               f"--user-data-dir={T.TMP / 'chrome_popup'}", "--window-size=1280,900", "about:blank"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            try:
                page = next(t for t in json.loads(urllib.request.urlopen(f"http://127.0.0.1:{T.DEVTOOLS}/json", timeout=2).read()) if t["type"] == "page")
                break
            except Exception:
                time.sleep(0.5)
        tab = T.Tab(page["webSocketDebuggerUrl"])
        tab.cmd("Emulation.setDeviceMetricsOverride", width=1280, height=900, deviceScaleFactor=1, mobile=False)
        sa = account("Asha Rao", "asha@example.com", {"age": 45, "station": "silkboard", "conditions": ["lung"], "replay_emails": False})
        sb = account("Bala K", "bala@example.com", {"age": 8, "station": "silkboard", "conditions": [], "replay_emails": False})

        def open_replay(session, width=1280, height=900, mobile=False):
            tab.cmd("Emulation.setDeviceMetricsOverride", width=width, height=height, deviceScaleFactor=1, mobile=mobile)
            tab.set_session(session)
            tab.goto(BASE + "/?pauseonalert=1")
            tab.wait("S.hours.length > 0 && document.getElementById('acctNav').textContent.includes('Log out')", 25)
            tab.pump(0.8)

        # ---- switch and header (desktop + phone) ----
        open_replay(sa)
        sw = tab.js("""(() => Array.from(document.querySelectorAll('.modeswitch a')).map(a => ({text: a.textContent.trim(), current: a.getAttribute('aria-current')})))()""")
        btns = tab.js("""(() => Array.from(document.querySelectorAll('#acctNav .btn-sm')).map(b => b.tagName + ':' + b.textContent))()""")
        check("W1 replay page: switch 'Replay demo | Live data' with Replay highlighted", [x["text"] for x in sw] == ["▶ Replay demo", "● Live data"]
              and sw[0]["current"] == "page" and sw[1]["current"] is None, str(sw))
        check("W2 Profile and Log out are buttons in the header", btns == ["A:Profile", "BUTTON:Log out"], str(btns))
        tab.js("window.scrollTo(0, 0)")
        shot(tab, "switch_replay_desktop.png")
        tab.goto(BASE + "/live.html")
        tab.wait("document.getElementById('bannerText').textContent !== 'Loading...'", 25)
        tab.pump(0.8)
        sw = tab.js("""(() => Array.from(document.querySelectorAll('.modeswitch a')).map(a => a.getAttribute('aria-current')))()""")
        check("W3 live page: the same switch with Live highlighted", sw == [None, "page"], str(sw))
        check("W4 no JavaScript errors on the live page", not tab.errors, str(tab.errors))
        shot(tab, "switch_live_desktop.png")
        tab.cmd("Emulation.setDeviceMetricsOverride", width=390, height=844, deviceScaleFactor=2, mobile=True)
        tab.goto(BASE + "/live.html"); tab.wait("document.getElementById('bannerText').textContent !== 'Loading...'", 25); tab.pump(0.8)
        wid = tab.js("(() => { const r = document.querySelector('.modeswitch').getBoundingClientRect(); return [Math.round(r.width), document.documentElement.clientWidth]; })()")
        check("W5 phone (390 px): the switch spans the full content width", wid[0] >= wid[1] - 40, str(wid))
        shot(tab, "switch_live_mobile.png")

        # ---- pop-ups for two profiles at the same hour ----
        open_replay(sa)
        pa = popup_at(tab, HOUR)
        check("A1 account A (lung disease): an alert pop-up appears", bool(pa), str(pa))
        check("A2 pop-up = forecast headline + 1-2 profile lines, trend, best time, 1 tip; each line with a citation",
              pa and 4 <= len(pa["lines"]) <= 5 and all(s.strip() for s in pa["sources"]), str(pa and pa["lines"]))
        best = [l for l in (pa or {}).get("lines", []) if l.startswith(("Usually cleanest", "No clearly better", "Limit outdoor"))]
        check("A3 A's pop-up: lung-disease line, trend, best time from the station pattern (with 'How is this calculated?'), one tip",
              pa and pa["lines"][0].startswith("Lung disease") and any(l.startswith("Next 24 h: ") for l in pa["lines"]) and len(best) == 1
              and "How is this calculated?" in best[0] and sum(l.startswith("Tip") for l in pa["lines"]) == 1, str(best))
        check("A4 no JavaScript errors on the replay page (A)", not tab.errors, str(tab.errors))
        shot(tab, "popup_lung_desktop.png")
        tips = lambda p: [l for l in (p or {}).get("lines", []) if l.startswith("Tip")]      # noqa: E731
        pa2 = popup_at(tab, HOUR2)
        check("A5 the next alert for A (issued at another hour) shows a different tip", pa2 and tips(pa) != tips(pa2), f"{tips(pa)} -> {tips(pa2)}")
        pa3 = popup_at(tab, HOUR)
        check("A6 the same alert again (back to the same hour) shows the same tip", pa3 and tips(pa3) == tips(pa), f"{tips(pa)} / {tips(pa3)}")
        # icons: the trend arrow follows the direction (this hour: falling -> down-right arrow); the best-time line has a clock, not an arrow
        ic = tab.js("""(() => { const t = document.querySelector('#toasts .pa-trend'), b = document.querySelector('#toasts .pa-best_time');
            return { trendClass: t.className, trendMarker: getComputedStyle(t).listStyleType, bestMarker: getComputedStyle(b).listStyleType,
                     bestIcon: getComputedStyle(b, '::before').maskImage || getComputedStyle(b, '::before').webkitMaskImage }; })()""")
        check("I1 'Next 24 h: falling' shows the falling arrow (dir-down, ↘), not the rising one", "dir-down" in ic["trendClass"] and "↘" in ic["trendMarker"]
              and "↗" not in ic["trendMarker"], str(ic))
        check("I2 the 'Usually cleanest' line has a clock icon and no arrow", ic["bestMarker"] == "none" and "svg" in (ic["bestIcon"] or ""), str(ic))
        # modal while paused: centred dialog with a dimmed backdrop covering the page (incl. the Personal advice card); Esc closes, replay stays paused
        md = tab.js("""(() => { const box = document.getElementById('toasts'), t = box.querySelector('.toast'), r = t.getBoundingClientRect(),
            adv = document.querySelector('.foryou').getBoundingClientRect(), hit = document.elementFromPoint(adv.left + 10, adv.top + 10);
            return { modal: box.classList.contains('modal'), role: t.getAttribute('role'), ariaModal: t.getAttribute('aria-modal'),
                     cx: Math.round(r.left + r.width / 2), cy: Math.round(r.top + r.height / 2), vw: document.documentElement.clientWidth, vh: innerHeight,
                     backdrop: getComputedStyle(box).backgroundColor, adviceCovered: !!hit && (hit === box || box.contains(hit)),
                     focus: document.activeElement && document.activeElement.id }; })()""")
        check("M1 desktop: while paused the alert is a centred modal dialog (role alertdialog, aria-modal) with a dimmed backdrop",
              md["modal"] and md["role"] == "alertdialog" and md["ariaModal"] == "true" and abs(md["cx"] - md["vw"] / 2) < 4 and abs(md["cy"] - md["vh"] / 2) < 40
              and md["backdrop"] not in ("rgba(0, 0, 0, 0)", "transparent"), str(md))
        check("M2 the Personal advice card is no longer covered by a corner pop-up: the backdrop dims the whole page", md["adviceCovered"], str(md))
        check("M3 keyboard focus moves into the dialog (Continue replay)", md["focus"] == "toastContinue", str(md))
        tab.cmd("Input.dispatchKeyEvent", type="keyDown", key="Escape", code="Escape", windowsVirtualKeyCode=27)
        tab.cmd("Input.dispatchKeyEvent", type="keyUp", key="Escape", code="Escape", windowsVirtualKeyCode=27)
        tab.pump(0.3)
        esc = tab.js("({ alert: !!S.alert, toasts: document.getElementById('toasts').children.length, modal: document.getElementById('toasts').classList.contains('modal'), playing: S.playing })")
        check("M4 Esc closes the dialog like Dismiss (no backdrop left, replay stays paused)", esc == {"alert": False, "toasts": 0, "modal": False, "playing": False}, str(esc))
        open_replay(sa, 390, 844, True)
        popup_at(tab, HOUR)
        sh = tab.js("""(() => { const t = document.querySelector('#toasts .toast').getBoundingClientRect(), ban = document.getElementById('simTimeShort');
            const bm = document.querySelector('.banner .bn-main');
            return { bottom: Math.round(t.bottom), left: Math.round(t.left), width: Math.round(t.width), vw: innerWidth, vh: innerHeight,
                     short: ban.textContent, shortVisible: ban.offsetParent !== null, longHidden: document.getElementById('simTime').offsetParent === null,
                     clipped: bm.scrollWidth > bm.clientWidth + 1 || ban.getBoundingClientRect().right > innerWidth }; })()""")
        check("M5 phone: the alert is a bottom sheet (full width, at the bottom of the screen)", abs(sh["bottom"] - sh["vh"]) <= 1 and sh["left"] == 0
              and sh["width"] == sh["vw"], str(sh))
        check("S1 phone banner shows the short simulated time '24 Apr, 02:00 IST' in full (nothing cut off)", sh["short"] == "24 Apr, 02:00 IST"
              and sh["shortVisible"] and sh["longHidden"] and not sh["clipped"], str(sh))
        shot(tab, "popup_lung_mobile.png")
        tab.cmd("Network.deleteCookies", name="aqi_session", url=BASE)
        tab.goto(BASE + "/login.html"); tab.pump(0.5)
        check("L1 login page (signed out): no 'Replay demo | Live data' switch", tab.js("!document.querySelector('.modeswitch')"))
        tab.cmd("Emulation.setDeviceMetricsOverride", width=390, height=844, deviceScaleFactor=2, mobile=True)
        tab.goto(BASE + "/login.html"); tab.pump(0.5)
        bm = tab.js("""(() => { const s = document.querySelector('.brand-short'), r = s.getBoundingClientRect();
            return { short: getComputedStyle(s).display !== 'none', full: getComputedStyle(document.querySelector('.brand-full')).display, text: s.textContent,
                     lines: Math.round(r.height / parseFloat(getComputedStyle(s).lineHeight)), right: Math.round(r.right), vw: innerWidth }; })()""")
        check("L2 phone: the top bar shows the short title 'AQ & Health Risk Framework' on one line", bm["short"] and bm["full"] == "none"
              and bm["text"] == "AQ & Health Risk Framework" and bm["lines"] == 1 and bm["right"] <= bm["vw"], str(bm))

        open_replay(sb)
        pb = popup_at(tab, HOUR)
        check("B1 account B (child, age 8): an alert pop-up appears with the child line", pb and pb["lines"][0].startswith("Child"), str(pb and pb["lines"]))
        check("B2 the two profiles get different pop-ups at the same hour", pb and pa and pb["lines"][0] != pa["lines"][0])
        check("B3 no JavaScript errors on the replay page (B)", not tab.errors, str(tab.errors))
        shot(tab, "popup_child_desktop.png")
        open_replay(sb, 390, 844, True)
        popup_at(tab, HOUR)
        shot(tab, "popup_child_mobile.png")
        print("A pop-up:", json.dumps(pa, ensure_ascii=False, indent=1))
        print("B pop-up:", json.dumps(pb, ensure_ascii=False, indent=1))
        tab.ws.close()
    finally:
        chrome.kill()
        proc.kill()
    print()
    print("ALL PASSED" if not failures else f"{len(failures)} FAILED: {failures}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
