"""Overnight queue: the two comparison reruns with the OFFICIAL configuration (run_final.py, full config, run_info.json).
  1. window : cleaned data restricted to 2025-11-01 .. 2026-07-22 (same calendar split)  -> results/final_window/
  2. user   : the user's earlier gap-filled hourly files                                   -> results/final_user_files/
Horizons 1, 6, 12, 24. Runs sequentially; progress in results/final_*/log.txt.
usage (project root): python model/run_comparisons.py"""
import os, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
JOBS = [
    ("final_window", ROOT / "data" / "processed" / "clean_hourly_all_stations.pkl", "2025-11-01:2026-07-22"),
    ("final_user_files", ROOT / "data" / "processed_user" / "hourly_user.pkl", ""),
]
env = dict(os.environ, LOKY_MAX_CPU_COUNT="8")
subprocess.run([PY, str(ROOT / "model" / "build_user_hourly.py")], check=True, cwd=ROOT)
for name, pkl, window in JOBS:
    out = ROOT / "results" / name
    out.mkdir(parents=True, exist_ok=True)
    cmd = [PY, "-W", "ignore", "run_final.py", str(pkl), str(out / "csh"), "1,6,12,24"] + ([window] if window else [])
    with open(out / "log.txt", "w") as log:
        r = subprocess.run(cmd, cwd=ROOT / "model", env=env, stdout=log, stderr=subprocess.STDOUT)
    print(name, "exit", r.returncode, flush=True)
