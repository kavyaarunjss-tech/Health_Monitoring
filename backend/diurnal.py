"""Typical time-of-day pattern of PM2.5 and PM10 at a station ("usually cleanest / usually worst"), used instead of picking a best time from
the four AQI forecast points (CPCB AQI is a 24 h average, so its hourly forecasts barely say which hour of the day is cleaner).

Rule (user decision, 20 Oct 2026):
  * window: the 28 days BEFORE the current / simulated hour t, only hours <= t (data available at t; no leakage in replay); only measured hours
    (real_pm = 1, not gap-filled);
  * for every hour of the day: median PM2.5 and median PM10 over the window; an hour counts only if BOTH have values on >= 20 of the 28 days;
  * hour score = mean of (hour median / window median) for PM2.5 and PM10 (so both pollutants weigh equally);
  * 3-hour blocks: cleanest block within daytime (06:00-21:00), worst block over the whole day; a best time is shown only if the cleanest block's
    score is >= 20 % lower than the worst block's, otherwise "No clearly better time at this station".
Hour labels are hour-START (aq_clean), so block 13,14,15 = 1 pm to 4 pm.
"""
import sqlite3
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
FMT = "%Y-%m-%d %H:%M:%S"
DAYS, MIN_DAYS, MIN_DROP, BLOCK = 28, 20, 0.20, 3
DAY_START, DAY_END = 6, 21                          # daytime blocks must lie within 06:00-21:00

HOW = ("How is this calculated? We take the hourly PM2.5 and PM10 measured at this station in the 28 days before this hour (no later data), "
       "find the median for each hour of the day, and compare 3-hour blocks between 6 am and 9 pm with the worst 3-hour block of the day. "
       "A time is shown only if it is at least 20% cleaner and each of those hours has measurements on at least 20 of the 28 days. "
       "It is a typical pattern, not a forecast. (The CPCB AQI is a 24-hour average, so the AQI forecasts themselves cannot tell which hour "
       "of the day is cleaner.) WHO advises planning when and where to be active to reduce exposure [5].")


def clock(h):
    h %= 24
    return f"{12 if h % 12 == 0 else h % 12} {'am' if h < 12 else 'pm'}"


def block_label(start):
    a, b = clock(start), clock(start + BLOCK)
    return f"{a.split()[0]}–{b}" if a.split()[1] == b.split()[1] else f"{a}–{b}"


def profile_from_rows(rows, t):
    """rows: (datetime 'YYYY-mm-dd HH:MM:SS', pm25, pm10, real_pm) in any order; only rows in (t - 28 d, t] are used, whatever is passed."""
    t0 = datetime.strptime(t, FMT)
    lo = (t0 - timedelta(days=DAYS)).strftime(FMT)
    use = [r for r in rows if lo < r[0] <= t and (r[3] is None or int(r[3]) == 1)]
    by = {h: {"pm25": {}, "pm10": {}} for h in range(24)}
    for dt, p25, p10, _ in use:
        h, day = int(dt[11:13]), dt[:10]
        if p25 is not None and p25 == p25:
            by[h]["pm25"][day] = float(p25)
        if p10 is not None and p10 == p10:
            by[h]["pm10"][day] = float(p10)
    all25 = [v for h in by for v in by[h]["pm25"].values()]
    all10 = [v for h in by for v in by[h]["pm10"].values()]
    out = {"window_from": lo, "window_to": t, "hours_used": len(use)}
    if not all25 or not all10:
        return {**out, "status": "not_enough_data", "valid_hours": 0}
    o25, o10 = median(all25), median(all10)
    score, ndays = {}, {}
    for h in range(24):
        n = min(len(by[h]["pm25"]), len(by[h]["pm10"]))
        ndays[h] = n
        if n >= MIN_DAYS and o25 > 0 and o10 > 0:
            score[h] = (median(by[h]["pm25"].values()) / o25 + median(by[h]["pm10"].values()) / o10) / 2
    out.update(valid_hours=len(score), days_per_hour=ndays)
    blocks = {s: sum(score[(s + i) % 24] for i in range(BLOCK)) / BLOCK for s in range(24) if all((s + i) % 24 in score for i in range(BLOCK))}
    day_blocks = {s: v for s, v in blocks.items() if s >= DAY_START and s + BLOCK <= DAY_END}
    if not blocks or not day_blocks:
        return {**out, "status": "not_enough_data"}
    best_s = min(day_blocks, key=lambda s: (day_blocks[s], s))
    worst_s = max(blocks, key=lambda s: (blocks[s], -s))
    drop = (blocks[worst_s] - day_blocks[best_s]) / blocks[worst_s] if blocks[worst_s] > 0 else 0.0
    out.update(best={"start": best_s, "label": block_label(best_s), "score": round(day_blocks[best_s], 3)},
               worst={"start": worst_s, "label": block_label(worst_s), "score": round(blocks[worst_s], 3)}, drop=round(drop, 3))
    out["status"] = "ok" if drop >= MIN_DROP else "no_clear"
    return out


@lru_cache(maxsize=4096)
def _cached(db, table, station, t):
    with sqlite3.connect(db, timeout=30) as c:
        lo = (datetime.strptime(t, FMT) - timedelta(days=DAYS)).strftime(FMT)
        rows = c.execute(f"SELECT datetime, pm25, pm10, real_pm FROM {table} WHERE station=? AND datetime>? AND datetime<=?", (station, lo, t)).fetchall()
    return profile_from_rows(rows, t)


def replay_profile(station, t):
    return _cached(str(ROOT / "data" / "replay.db"), "replay_pm", station, t)


def live_profile(station, t):
    """t = label of the newest observation; the live database is rebuilt hourly, so the cache key includes t."""
    return _cached(str(ROOT / "data" / "aqi.db"), "hourly", station, t)
