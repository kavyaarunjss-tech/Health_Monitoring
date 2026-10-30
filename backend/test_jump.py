"""Headless test for "Skip to next pollution event (demo)".

Bug found 2026-10-17: from 19 Apr 09:00 the button jumped BACKWARDS (to 18 Apr 03:00, then 17 Apr 08:00). It looked for the next event HOUR (any hour with
AQI > 100); inside an episode that is simply the next hour, and "6 h before it" lies in the past.

Rules now: events are ONSETS (AQI reaching the user's alert level from below, or the CPCB category rising to Moderate or worse); search only forward from the
displayed hour; land 6 h before the onset; an onset whose lead hour is not after the displayed hour is skipped; none ahead -> "No more events in this period"
and the display does not move.

This test opens the real page in headless Chrome (?selftest=jump), presses the button from many start hours at Silk Board and Mysuru (validation and test
period, a lung-disease profile with alert level 101 and a healthy profile with 201), and verifies every jump against an INDEPENDENT computation of the onsets
from the database (it does not reuse the backend's find_onsets). No e-mail is sent (fake mode).

usage (project root, aqi env):  python backend\\test_jump.py        (set CHROME_PATH if Chrome is not in the usual place)
"""
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TMP = Path(tempfile.mkdtemp(prefix="aqi_jumptest_"))
PORT = 8031
FMT = "%Y-%m-%d %H:%M:%S"
PERIODS = {"validation": ("2026-04-17 07:00:00", "2026-05-29 12:00:00"), "test": ("2026-05-29 14:00:00", "2026-07-21 23:00:00")}
STARTS = {"validation": ["2026-04-17 07:00:00", "2026-04-18 03:00:00", "2026-04-19 09:00:00", "2026-04-23 18:00:00", "2026-04-24 02:00:00",
                         "2026-05-05 12:00:00", "2026-05-20 00:00:00", "2026-05-28 18:00:00"],
          "test": ["2026-05-29 14:00:00", "2026-06-10 00:00:00", "2026-07-01 12:00:00", "2026-07-20 00:00:00"]}
CHAIN = 5
CHROME = os.environ.get("CHROME_PATH") or next((p for p in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                                                             r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                                                             r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe") if Path(p).exists()), None)
failures = []
counts = {"jumps": 0, "no_more": 0, "runs": 0}


def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  {extra}" if extra else ""))
    if not cond:
        failures.append(name)


# ---------------------------------------------------------------- independent reference (own category boundaries and own loops)
def cat_rank(a):
    return 0 if a <= 50 else 1 if a <= 100 else 2 if a <= 200 else 3 if a <= 300 else 4 if a <= 400 else 5


def reference_onsets(con, station, level, period):
    start, end = PERIODS[period]
    lo = (datetime.strptime(start, FMT) - timedelta(hours=1)).strftime(FMT)
    rows = con.execute("SELECT datetime, AQI FROM replay_obs WHERE station=? AND datetime BETWEEN ? AND ? AND AQI IS NOT NULL ORDER BY datetime",
                       (station, lo, end)).fetchall()
    out = []
    for i in range(1, len(rows)):
        (t0, a0), (t1, a1) = rows[i - 1], rows[i]
        if datetime.strptime(t1, FMT) - datetime.strptime(t0, FMT) != timedelta(hours=1) or t1 < start:
            continue
        a0, a1 = int(a0 + 0.5), int(a1 + 0.5)
        if (a0 < level <= a1) or (cat_rank(a1) > cat_rank(a0) and cat_rank(a1) >= 2):
            out.append(t1)
    return out


def reference_jump(onsets, hours, from_idx):
    """First onset whose lead hour (first simulated hour at or after onset-6h, before the onset) comes after the displayed hour."""
    for on in onsets:
        on_dt = datetime.strptime(on, FMT)
        for k, h in enumerate(hours):
            hd = datetime.strptime(h, FMT)
            if on_dt - timedelta(hours=6) <= hd < on_dt:
                if k > from_idx:
                    return on, k
                break
    return None, None


# ---------------------------------------------------------------- run the real page
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


def run_page(station, period, profile):
    q = {"selftest": "jump", "station": station, "period": period, "profile": profile, "chain": CHAIN, "starts": "|".join(STARTS[period])}
    url = f"http://127.0.0.1:{PORT}/?" + urllib.parse.urlencode(q, quote_via=urllib.parse.quote)
    prof = TMP / f"chrome_{station}_{period}_{profile}"
    r = subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-sandbox", f"--user-data-dir={prof}", "--virtual-time-budget=300000", "--dump-dom", url],
                       capture_output=True, text=True, timeout=600, encoding="utf-8", errors="replace")
    m = re.search(r'<pre id="selftest"[^>]*>(.*?)</pre>', r.stdout, flags=re.S)
    if not m:
        raise SystemExit(f"no self-test output for {station}/{period}/{profile}")
    import html
    return json.loads(html.unescape(m.group(1)))


def main():
    if not CHROME:
        raise SystemExit("Chrome/Edge not found; set CHROME_PATH")
    con = sqlite3.connect(ROOT / "data" / "replay.db")
    proc = start_server()
    try:
        fake = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/email/outbox").read())["fake"]
        check("T0 test server is in fake e-mail mode", fake is True)
        if not fake:
            raise SystemExit("refusing to continue: not in fake mode")
        example = None
        for station in ("silkboard", "mysuru"):
            for period in ("validation", "test"):
                hours = [r[0] for r in con.execute("SELECT DISTINCT origin FROM replay_fc WHERE period=? AND station=? AND origin BETWEEN ? AND ? ORDER BY origin",
                                                   ("validation" if period == "validation" else "test", station, *PERIODS[period]))]
                for profile, level in (("lung", 101), ("lung51", 51), ("healthy151", 151), ("healthy", 201)):   # 51 and 151 are not Moderate/Poor boundaries: they exercise the level rule on its own
                    out = run_page(station, period, profile)
                    counts["runs"] += 1
                    onsets = reference_onsets(con, station, level, period)
                    bad, last_to = [], {}
                    for r in out["results"]:
                        counts["jumps"] += 1
                        from_idx = hours.index(r["from"])
                        exp_on, exp_k = reference_jump(onsets, hours, from_idx)
                        tag = f"{station}/{period}/{profile} start {r['start']} step {r['step']} from {r['from']}"
                        if r["moved"]:
                            if not r["to"] > r["from"]:
                                bad.append(f"BACKWARDS or no move: {tag} -> {r['to']}")
                            if exp_on is None:
                                bad.append(f"moved but the reference says no event ahead: {tag} -> {r['to']}")
                            else:
                                lead = datetime.strptime(r["onset"], FMT) - datetime.strptime(r["to"], FMT)
                                if r["onset"] not in onsets:
                                    bad.append(f"landed before something that is not an onset: {tag} onset {r['onset']}")
                                if not (timedelta(0) < lead <= timedelta(hours=6)):
                                    bad.append(f"lead {lead} not within (0, 6 h]: {tag}")
                                exact = (datetime.strptime(r["onset"], FMT) - timedelta(hours=6)).strftime(FMT)
                                if exact in hours and r["to"] != exact:
                                    bad.append(f"6 h before is available ({exact}) but landed {r['to']}: {tag}")
                                if r["onset"] != exp_on or r["to"] != hours[exp_k]:
                                    bad.append(f"not the first eligible onset: {tag} got onset {r['onset']} -> {r['to']}, expected {exp_on} -> {hours[exp_k]}")
                            if r["start"] in last_to and not r["to"] > last_to[r["start"]]:
                                bad.append(f"chain not increasing: {tag}")
                            last_to[r["start"]] = r["to"]
                            if example is None and station == "silkboard" and period == "validation" and profile == "lung" and r["start"] == "2026-04-19 09:00:00":
                                example = (r["from"], r["to"], r["onset"])
                        else:
                            counts["no_more"] += 1
                            if exp_on is not None:
                                bad.append(f"did not move although an onset was ahead ({exp_on}): {tag}")
                            if r["msg"] != "No more events in this period":
                                bad.append(f"no message when nothing is ahead: {tag} msg '{r['msg']}'")
                    n_on = len(onsets)
                    check(f"{station:10s} {period:10s} {profile:7s} (alert {level}, {n_on:3d} onsets): {len(out['results'])} presses all correct", not bad and out["level"] == level,
                          f"({bad[:2]})" if bad else "")
        check("T1 the reported bug case (Silk Board, from 19 Apr 09:00) now moves FORWARD to 6 h before a real onset", example is not None and example[1] > example[0],
              f"(from {example[0] if example else '-'} to {example[1] if example else '-'}, onset {example[2] if example else '-'})")
        check("T2 jumps were exercised and the 'no more events' case too", counts["jumps"] > 80 and counts["no_more"] > 5, f"({counts})")
    finally:
        proc.terminate()
    print("\nALL PASSED" if not failures else f"\n{len(failures)} FAILED: {failures}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
