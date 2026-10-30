"""The site looks the same without internet: the Inter font is bundled in frontend/fonts/ (woff2, SIL OFL) and no page requests anything outside
this computer. Chrome (DevTools protocol) blocks every https request, records every request each page makes, and checks on the login, sign-up,
replay, live and profile pages that the Inter font is loaded from the local server, the body text renders in Inter, and there are no console errors.
Own fake-mode server on port 8037 (DevTools 9337), temporary users.db; never port 8000.

usage (project root, aqi env):  python backend\\test_fonts.py
"""
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_pages_logged_in as T  # noqa: E402

T.PORT, T.DEVTOOLS = 8037, 9337
T.BASE = BASE = f"http://127.0.0.1:{T.PORT}"
check, failures = T.check, T.failures
FONTS = T.ROOT / "frontend" / "fonts"


class RecTab(T.Tab):
    """Tab that also records every network request and every failed one."""
    def __init__(self, ws_url):
        self.requests, self.failed = [], []
        super().__init__(ws_url)

    def _event(self, msg):
        m, p = msg.get("method"), msg.get("params", {})
        if m == "Network.requestWillBeSent":
            self.requests.append(p["request"]["url"])
        elif m == "Network.loadingFailed":
            self.failed.append(p.get("errorText", ""))
        super()._event(msg)


def main():
    # files and licence
    files = sorted(p.name for p in FONTS.glob("*.woff2"))
    check("F1 Inter woff2 files are bundled in frontend/fonts/ (latin + latin-ext)", files == ["inter-latin-ext-wght.woff2", "inter-latin-wght.woff2"], str(files))
    check("F2 every bundled file really is woff2 (magic 'wOF2')", all((FONTS / f).read_bytes()[:4] == b"wOF2" for f in files))
    check("F3 the font licence (SIL Open Font License) is bundled next to the fonts", "SIL OPEN FONT LICENSE" in (FONTS / "OFL.txt").read_text(encoding="utf-8"))
    src = "".join(p.read_text(encoding="utf-8") for p in (T.ROOT / "frontend").glob("*.*") if p.suffix in (".html", ".css", ".js") and not p.name.startswith("_"))
    check("F4 no page, stylesheet or script refers to Google Fonts any more", "googleapis" not in src and "gstatic" not in src)

    proc = T.start_server()
    chrome = subprocess.Popen([T.CHROME, "--headless=new", "--disable-gpu", "--no-sandbox", f"--remote-debugging-port={T.DEVTOOLS}",
                               f"--user-data-dir={T.TMP / 'chrome_fonts'}", "--window-size=1366,900", "about:blank"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        r = urllib.request.urlopen(BASE + "/fonts/inter-latin-wght.woff2")
        check("F5 the server serves the font file as font/woff2 (200, Cache-Control no-cache)", r.status == 200 and r.headers.get("Content-Type") == "font/woff2"
              and r.headers.get("Cache-Control") == "no-cache",
              f"{r.status} {r.headers.get('Content-Type')} {r.headers.get('Cache-Control')}")
        for _ in range(60):
            try:
                page = next(t for t in json.loads(urllib.request.urlopen(f"http://127.0.0.1:{T.DEVTOOLS}/json", timeout=2).read()) if t["type"] == "page")
                break
            except Exception:
                time.sleep(0.5)
        tab = RecTab(page["webSocketDebuggerUrl"])
        tab.cmd("Network.setCacheDisabled", cacheDisabled=True)
        tab.cmd("Network.setBlockedURLs", urls=["https://*"])          # "no internet": anything outside this computer would fail
        session = T.api_session(first=True)

        def visit(name, url, ready, login):
            tab.cmd("Network.deleteCookies", name="aqi_session", url=BASE)
            if login:
                tab.set_session(session)
            tab.requests.clear(); tab.failed.clear()
            tab.goto(url)
            tab.wait(ready, 25)
            tab.js("document.fonts.ready.then(() => true)")
            tab.pump(0.8)
            info = tab.js("""(() => ({ faces: Array.from(document.fonts).filter(f => f.family.replace(/"/g, '') === 'Inter').map(f => f.status),
                                        inter: document.fonts.check('16px Inter'), family: getComputedStyle(document.body).fontFamily }))()""")
            external = [u for u in tab.requests if not u.startswith(BASE) and not u.startswith("data:")]
            fonts = [u for u in tab.requests if "/fonts/" in u]
            check(f"{name}: no request leaves this computer; Inter loaded from /fonts/; body font is Inter; no console errors",
                  not external and fonts and "loaded" in info["faces"] and info["inter"] and info["family"].startswith('Inter') and not tab.errors and not tab.failed,
                  f"(external {external}, font files {[u.rsplit('/', 1)[-1] for u in fonts]}, faces {info['faces']}, errors {tab.errors + tab.failed})")

        # branding: text only (no logo), the full title on wide screens and the login card, tab titles "<page> · AQ & Health Risk Framework"
        for pg in ("index.html", "live.html", "login.html", "signup.html", "profile.html", "forgot.html", "reset.html"):
            h = (T.ROOT / "frontend" / pg).read_text(encoding="utf-8")
            if "<svg" in h or 'class="logo"' in h or "Karnataka Air Quality &amp; Health Alerts" in h or "&middot; AQ &amp; Health Risk Framework</title>" not in h:
                failures.append("B1 " + pg)
        check("B1 no logo on any page; every tab title is '<page> · AQ & Health Risk Framework'", not [f for f in failures if f.startswith("B1")])
        tab.goto(BASE + "/login.html"); tab.pump(0.5)
        br = tab.js("""(() => ({ full: getComputedStyle(document.querySelector('.brand-full')).display, short: getComputedStyle(document.querySelector('.brand-short')).display,
            text: document.querySelector('.brand-full').textContent, sub: document.querySelector('.brand-sub').textContent,
            card: document.querySelector('.auth-head .proj').textContent, title: document.title, svg: document.querySelectorAll('svg').length }))()""")
        check("B2 desktop (1366 px): top bar shows the full title and the subtitle; the login card shows the full title; no icon",
              br["full"] != "none" and br["short"] == "none" and br["text"] == "Integrated Air Quality & Health Risk Prediction Framework"
              and br["sub"] == "for Sustainable Urban Environments · Karnataka" and br["card"] == br["text"] and br["svg"] == 0
              and br["title"] == "Log in · AQ & Health Risk Framework", str(br))
        visit("P1 login", BASE + "/login.html", "!!document.getElementById('loginForm')", False)
        visit("P2 sign-up", BASE + "/signup.html", "!!document.getElementById('signupForm')", False)
        visit("P3 replay", BASE + "/", "document.getElementById('simTime').textContent.includes('IST')", True)
        visit("P4 live", BASE + "/live.html", "document.getElementById('bannerText').textContent !== 'Loading...'", True)
        visit("P5 profile", BASE + "/profile.html", "document.getElementById('pName').value !== ''", True)
        tab.ws.close()
    finally:
        chrome.kill()
        proc.kill()
    print()
    print("ALL PASSED" if not failures else f"{len(failures)} FAILED: {failures}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
