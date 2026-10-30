"""Headless test of the replay alert pop-up lifecycle (pause-on-alert and the 10-second minimum).

Problem (user, 17 Oct 2026): during replay at 1 h/s a +1 h alert vanished after ~1 s because its target hour passed, so it could not be read.
New behaviour: pause-on-alert (default ON in replay) stops the replay clock and shows the pop-up with "Continue replay" and "Dismiss"; with it OFF each
pop-up stays at least 10 real seconds (or until dismissed/replaced) and is marked "(target hour now passed)"; a newer alert replaces a stale pop-up at once,
an escalation replaces a live one at once; one pop-up at a time. Live mode is unchanged.

Three page runs (headless Chrome, fake e-mail mode):
  1. ?selftest=popuplogic  deterministic checks with a controllable clock (visible at 9.8 s, gone after 10 s, replacement, escalation, buttons, pinning)
  2. ?selftest=popup&mode=pause    real playback at 1 h/s: the first alert stops the clock for >= 10 s, Continue restarts it, Dismiss leaves it paused
  3. ?selftest=popup&mode=nopause  real playback at 1 h/s: every pop-up that ends by itself was visible >= 10 s and was marked when its target hour passed

usage (project root, aqi env):  python backend\\test_alert_popup.py        (set CHROME_PATH if Chrome is not in the usual place)
"""
import html
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TMP = Path(tempfile.mkdtemp(prefix="aqi_popuptest_"))
PORT = 8032
CHROME = os.environ.get("CHROME_PATH") or next((p for p in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                                                             r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                                                             r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe") if Path(p).exists()), None)
failures = []


def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  {extra}" if extra else ""))
    if not cond:
        failures.append(name)


def start_server():
    env = dict(os.environ, AQI_EMAIL_FAKE="1", AQI_RATE_FILE=str(TMP / "rate.json"), AQI_PROFILE_FILE=str(TMP / "profile.json"))
    log = open(TMP / "server.log", "w")
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "backend.app:app", "--port", str(PORT)], cwd=ROOT, env=env, stdout=log, stderr=log)
    for _ in range(60):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/meta", timeout=2)
            return proc
        except Exception:
            time.sleep(0.5)
    proc.kill()
    raise SystemExit("server did not start")


def run_page(query, budget_ms, tag):
    url = f"http://127.0.0.1:{PORT}/?" + urllib.parse.urlencode(query, quote_via=urllib.parse.quote)
    r = subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-sandbox", f"--user-data-dir={TMP / ('chrome_' + tag)}", f"--virtual-time-budget={budget_ms}",
                        "--dump-dom", url], capture_output=True, text=True, timeout=900, encoding="utf-8", errors="replace")
    m = re.search(r'<pre id="selftest"[^>]*>(.*?)</pre>', r.stdout, flags=re.S)
    if not m:
        raise SystemExit(f"no self-test output for {tag}")
    return json.loads(html.unescape(m.group(1)))


def main():
    if not CHROME:
        raise SystemExit("Chrome/Edge not found; set CHROME_PATH")
    proc = start_server()
    try:
        fake = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/email/outbox").read())["fake"]
        check("T0 test server is in fake e-mail mode", fake is True)
        if not fake:
            raise SystemExit("refusing to continue: not in fake mode")

        # 1. deterministic lifecycle checks
        out = run_page({"selftest": "popuplogic"}, 60000, "logic")
        for r in out["results"]:
            check(r["name"], r["ok"], r["extra"])

        # 2. pause on alert, real playback
        p = run_page({"selftest": "popup", "mode": "pause", "speed": 1, "start": "2026-04-18 00:00:00"}, 600000, "pause")
        check("P1 the first alert stops the replay clock", p.get("alertRaised") is True and p.get("title"), f"({p.get('title')})")
        check("P2 the pop-up has 'Continue replay' and 'Dismiss'", p["buttons"] == {"continue": True, "dismiss": True})
        h = p["held10s"]
        check("P3 for 10 s the simulated time does not advance, the pop-up stays and the replay stays stopped", h == {"moved": False, "toastGone": False, "playingAgain": False}, f"({h})")
        check("P4 'Continue replay' removes the pop-up and restarts the clock, which then advances", p["afterContinue"] == {"toasts": 0, "playing": True} and p["advancedAfterContinue"] is True,
              f"({p['afterContinue']}, advanced {p['advancedAfterContinue']})")
        check("P5 a second alert pauses the replay again", p.get("secondAlert") is True)
        check("P6 'Dismiss' removes the pop-up and the replay stays paused", p.get("afterDismiss") == {"toasts": 0, "playing": False} and p.get("stayedPausedAfterDismiss") is True,
              f"({p.get('afterDismiss')}, stayed paused {p.get('stayedPausedAfterDismiss')})")

        # 3. pause off, real playback
        n = run_page({"selftest": "popup", "mode": "nopause", "speed": 1, "seconds": 90, "start": "2026-04-18 00:00:00"}, 300000, "nopause")
        eps = n["episodes"]
        retired = [e for e in eps if e["endedBy"] == "retired"]
        print(f"     episodes: {len(eps)} (retired by themselves {len(retired)}, replaced {sum(e['endedBy'] == 'replaced' for e in eps)}); "
              + ", ".join(f"{e['visibleSeconds']}s/{e['endedBy']}" for e in eps[:8]))
        check("N1 pop-ups were raised and some ended by themselves (so the minimum could be tested)", len(eps) >= 3 and len(retired) >= 1, f"({len(eps)} episodes, {len(retired)} retired)")
        short = [e for e in retired if e["visibleSeconds"] < 9.6]
        check("N2 every pop-up that ended by itself had been visible for at least 10 s", not short, f"(shortest retired {min([e['visibleSeconds'] for e in retired] or [0])} s; too short: {short[:2]})")
        stale = [e for e in eps if e["staleSeconds"] > 0]
        check("N3 pop-ups stayed on screen after their target hour passed and said so", len(stale) >= 1 and all(e["marked"] for e in stale),
              f"({len(stale)} episodes with a passed target; stale time {[e['staleSeconds'] for e in stale][:5]} s)")
    finally:
        proc.terminate()
    print("\nALL PASSED" if not failures else f"\n{len(failures)} FAILED: {failures}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
