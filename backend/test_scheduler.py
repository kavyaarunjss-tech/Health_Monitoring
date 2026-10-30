"""Tests for the automatic-update scheduler (APScheduler inside the backend). Uses a harmless stub instead of the real fetch / e-mail commands:
no network, no e-mail, no change to your database.

usage (project root, aqi env):  python backend\\test_scheduler.py
"""
import os
import sys
import tempfile
import time
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="aqi_schedtest_"))
os.environ.update({"AQI_SCHEDULER": "1", "AQI_SCHEDULER_DRYRUN": "1", "AQI_DRY_SLEEP": "2", "AQI_EMAIL_FAKE": "1",
                   "AQI_STATUS_FILE": str(TMP / "status.json"), "AQI_UPDATE_LOG": str(TMP / "log.txt"),
                   "AQI_RATE_FILE": str(TMP / "rate.json"), "AQI_PROFILE_FILE": str(TMP / "profile.json")})
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from fastapi.testclient import TestClient  # noqa: E402
import backend.app as appmod  # noqa: E402
import scheduler as sched  # noqa: E402

failures = []


def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  {extra}" if extra else ""))
    if not cond:
        failures.append(name)


def wait_idle(client, timeout=20):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if client.get("/api/scheduler/status").json()["running"] is None:
            return True
        time.sleep(0.3)
    return False


with TestClient(appmod.app) as client:          # entering the context runs the app's start-up (lifespan) -> scheduler starts
    st = client.get("/api/scheduler/status").json()
    jobs = {j["id"]: j["next_run"] for j in st["jobs"]}
    check("S1 scheduler is enabled by AQI_SCHEDULER=1 with an hourly and a daily job", st["enabled"] and set(jobs) == {"hourly", "daily"}, f"({jobs})")
    check("S2 hourly job fires at minute 10, daily job at 03:40",
          jobs["hourly"] is not None and jobs["hourly"][14:16] == "10" and jobs["daily"][11:16] == "03:40", f"(next: {jobs})")

    r1 = client.post("/api/scheduler/run-now?kind=hourly").json()
    time.sleep(0.5)
    r2 = client.post("/api/scheduler/run-now?kind=hourly").json()
    check("S3 a second update requested while one is running is refused (never overlapped)", r1.get("started") is True and r2.get("started") is False, f"({r2})")
    check("S4 the running update is reported", client.get("/api/scheduler/status").json()["running"] is not None)
    check("S5 the update finishes", wait_idle(client))
    last = client.get("/api/scheduler/status").json()["last"]
    check("S6 a successful run records ok, both steps and its duration", last["ok"] and len(last["steps"]) == 2 and last["seconds"] >= 1.5, f"({last['steps']}, {last['seconds']} s)")
    check("S7 output is written to the update log", "dry run ok" in (TMP / "log.txt").read_text(encoding="utf-8"))

    os.environ["AQI_DRY_FAIL"] = "1"
    client.post("/api/scheduler/run-now?kind=daily")
    time.sleep(0.5)
    check("S8 the failing update finishes", wait_idle(client))
    last = client.get("/api/scheduler/status").json()["last"]
    check("S9 a failed update is recorded as failed and the e-mail step is skipped", last["ok"] is False and len(last["steps"]) == 1, f"({last['steps']})")
    os.environ.pop("AQI_DRY_FAIL")

    check("S10 bad kind is rejected", client.post("/api/scheduler/run-now?kind=weekly").status_code == 400)

# real command lists (stub switched off, e-mail check suppressed because fake mode is on)
sched.DRY = False
hourly, daily = sched._commands("hourly"), sched._commands("daily")
check("S11 the hourly job runs update_all.py --quick, the daily job the full update",
      "--quick" in hourly[0][1][-1] and "--quick" not in daily[0][1], f"({hourly[0][1][-2:]} / {daily[0][1][-1:]})")
check("S12 in fake mode no e-mail step is scheduled", len(hourly) == 1 and len(daily) == 1)

# disabled by default
sched.shutdown()
os.environ.pop("AQI_SCHEDULER")
with TestClient(appmod.app) as client:
    check("S13 without AQI_SCHEDULER=1 nothing is scheduled and run-now is refused (409)",
          client.get("/api/scheduler/status").json()["enabled"] is False and client.post("/api/scheduler/run-now").status_code == 409)

print("\nALL PASSED" if not failures else f"\n{len(failures)} FAILED: {failures}")
sys.exit(1 if failures else 0)
