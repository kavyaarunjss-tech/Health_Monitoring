"""Headless test of the 'Test notification' button and the red 'Server not running' bar (replay + live pages).

  1. ?selftest=servernotif   stubs window.Notification (granted / blocked / asked / unsupported) and window.fetch (fails, then recovers)
  2. the page opened as a file:// (server not running): the red bar is visible with the start command, on both pages

Uses its own fake-mode server on port 8033 (never port 8000, which may be the user's own server).

usage (project root, aqi env):  python backend\\test_server_bar.py        (set CHROME_PATH if Chrome is not in the usual place)
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
TMP = Path(tempfile.mkdtemp(prefix="aqi_servbartest_"))
PORT = 8033
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


def dump(url, budget_ms, tag):
    r = subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-sandbox", f"--user-data-dir={TMP / ('chrome_' + tag)}", f"--virtual-time-budget={budget_ms}",
                        "--dump-dom", url], capture_output=True, text=True, timeout=300, encoding="utf-8", errors="replace")
    return r.stdout


def main():
    if not CHROME:
        raise SystemExit("Chrome/Edge not found; set CHROME_PATH")
    proc = start_server()
    try:
        out = dump(f"http://127.0.0.1:{PORT}/?selftest=servernotif", 60000, "notif")
        m = re.search(r'<pre id="selftest"[^>]*>(.*?)</pre>', out, flags=re.S)
        if not m:
            raise SystemExit("no self-test output")
        for r in json.loads(html.unescape(m.group(1)))["results"]:
            check(r["name"], r["ok"], r["extra"])

        # server not running: the page opened as a file
        for page in ("index.html", "live.html"):
            dom = dump((ROOT / "frontend" / page).as_uri(), 8000, "file_" + page[:4])
            bar = re.search(r'<div id="serverDown"([^>]*)>(.*?)</div>', dom, flags=re.S)
            visible = bool(bar) and "hidden" not in bar.group(1)
            text = html.unescape(re.sub(r"<[^>]+>", "", bar.group(2))) if bar else ""
            check(f"F {page} opened as a file shows the red bar with the start command", visible and "Server not running" in text and "python -m uvicorn backend.app:app --port 8000" in text, text[:120])
    finally:
        proc.terminate()
    print("\nALL PASSED" if not failures else f"\n{len(failures)} FAILED: {failures}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
