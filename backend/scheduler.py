"""Automatic updates inside the backend (APScheduler). OFF unless AQI_SCHEDULER=1 (so tests and the replay demo never fetch data or send e-mail).

Jobs (timezone Asia/Kolkata):
  hourly  at minute 10 : update_all.py --quick   (OpenAQ API tail of the last 7 days, Open-Meteo forecast, rebuild database, live forecasts)
                         then notify_email.py --live   (only when .env e-mail is configured)
  daily   at 03:40     : update_all.py            (adds the S3 archive and the weather history)
One update runs at a time: a second request while one is running is refused (never queued, never overlapped). Each job runs as a SUBPROCESS, so a
crash or a hang cannot take the web server down (timeout 30 min). If the update step fails, the e-mail step is skipped and the database keeps its
previous content; live mode then shows older data with its "data is N hours old" banner.

Environment: AQI_SCHEDULER=1 enables; AQI_SCHEDULER_RUN_ON_START=1 also runs one hourly update 15 s after start-up.
Tests only: AQI_SCHEDULER_DRYRUN=1 runs a harmless stub instead of the real commands (AQI_DRY_SLEEP seconds, AQI_DRY_FAIL=1 to simulate a failure);
AQI_STATUS_FILE / AQI_UPDATE_LOG override the output files.
"""
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATUS_FILE = Path(os.environ.get("AQI_STATUS_FILE", ROOT / "data" / "scheduler_status.json"))
LOG_FILE = Path(os.environ.get("AQI_UPDATE_LOG", ROOT / "data" / "update_log.txt"))
DRY = os.environ.get("AQI_SCHEDULER_DRYRUN") == "1"
TIMEOUT_S = 1800
PY = sys.executable

_run_lock = threading.Lock()
_sched = None
_state = {"enabled": False, "running": None, "last": None}


def _commands(kind):
    if DRY:
        code = ("import os, sys, time; time.sleep(float(os.environ.get('AQI_DRY_SLEEP', '0'))); print('dry run ok'); "
                "sys.exit(1 if os.environ.get('AQI_DRY_FAIL') == '1' else 0)")
        return [("update (dry run)", [PY, "-c", code]), ("e-mail check (dry run)", [PY, "-c", "print('dry run ok')"])]
    cmds = [("update", [PY, str(ROOT / "backend" / "update_all.py")] + (["--quick"] if kind == "hourly" else []))]
    try:
        sys.path.insert(0, str(ROOT / "backend"))
        import notify_email as ne
        if ne.configured() and not ne.FAKE:
            cmds.append(("e-mail check", [PY, str(ROOT / "backend" / "notify_email.py"), "--live"]))
    except Exception:
        pass
    return cmds


def _save():
    try:
        STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATUS_FILE.write_text(json.dumps({"last": _state["last"]}, indent=1), encoding="utf-8")
    except Exception:
        pass


def run_job(kind="hourly", trigger="schedule"):
    """Run one update now. Returns {'started': bool, ...}. Refuses (does not queue) when another update is running."""
    if not _run_lock.acquire(blocking=False):
        return {"started": False, "reason": "an update is already running"}
    started = datetime.now()
    _state["running"] = {"kind": kind, "trigger": trigger, "started": started.isoformat(timespec="seconds")}
    steps, ok = [], True
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as log:
            log.write(f"\n===== {started:%Y-%m-%d %H:%M:%S} {kind} update ({trigger}) =====\n")
            for name, cmd in _commands(kind):
                t0 = time.time()
                try:
                    r = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_S, cwd=str(ROOT), encoding="utf-8", errors="replace")
                    rc, out = r.returncode, (r.stdout or "") + (r.stderr or "")
                except subprocess.TimeoutExpired:
                    rc, out = -1, f"timed out after {TIMEOUT_S} s"
                except Exception as e:  # noqa: BLE001
                    rc, out = -2, f"could not start: {type(e).__name__}"
                steps.append({"step": name, "returncode": rc, "seconds": round(time.time() - t0, 1)})
                log.write(f"--- {name}: exit {rc} in {time.time() - t0:.0f} s\n{out[-2500:]}\n")
                if rc != 0:
                    ok = False
                    log.write("later steps skipped\n")
                    break
    finally:
        finished = datetime.now()
        _state["last"] = {"kind": kind, "trigger": trigger, "started": started.isoformat(timespec="seconds"),
                          "finished": finished.isoformat(timespec="seconds"), "seconds": round((finished - started).total_seconds(), 1),
                          "ok": ok, "steps": steps}
        _state["running"] = None
        _save()
        _run_lock.release()
    return {"started": True, "ok": ok}


def start():
    """Start the scheduler if AQI_SCHEDULER=1 (called from the FastAPI lifespan). Returns the scheduler or None."""
    global _sched
    if os.environ.get("AQI_SCHEDULER") != "1" or _sched is not None:
        return _sched
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    try:
        _state["last"] = json.loads(STATUS_FILE.read_text(encoding="utf-8")).get("last")
    except Exception:
        pass
    s = BackgroundScheduler(timezone="Asia/Kolkata")
    common = dict(max_instances=1, coalesce=True, misfire_grace_time=900)
    s.add_job(run_job, CronTrigger(minute=10), args=("hourly", "schedule"), id="hourly", **common)
    s.add_job(run_job, CronTrigger(hour=3, minute=40), args=("daily", "schedule"), id="daily", **common)
    if os.environ.get("AQI_SCHEDULER_RUN_ON_START") == "1":
        s.add_job(run_job, "date", run_date=datetime.now() + timedelta(seconds=15), args=("hourly", "start-up"), id="startup")
    s.start()
    _sched = s
    _state["enabled"] = True
    return s


def shutdown():
    global _sched
    if _sched is not None:
        _sched.shutdown(wait=False)
        _sched = None
        _state["enabled"] = False


def status():
    jobs = []
    if _sched is not None:
        for j in _sched.get_jobs():
            jobs.append({"id": j.id, "next_run": j.next_run_time.strftime("%Y-%m-%d %H:%M:%S %Z") if j.next_run_time else None})
    return {"enabled": _state["enabled"], "dry_run": DRY, "running": _state["running"], "last": _state["last"], "jobs": jobs,
            "schedule": "hourly at minute 10 (quick update + e-mail check), daily at 03:40 (full update)"}
