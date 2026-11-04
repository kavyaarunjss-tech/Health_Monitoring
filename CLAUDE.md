# CLAUDE.md: Project memory for Claude Code

## Project
**Integrated Air Quality and Health Risk Prediction Framework for Sustainable Urban Environments**
Student research project (with a faculty guide). Forecast CPCB AQI 1–24 h ahead for 8 KSPCB monitoring
stations in Karnataka, and turn forecasts into personalised health-risk alerts on a local website.

The research/modelling phase is DONE and reproducible. The next phase is building the real-time system
(see "Build plan"). This file summarises everything decided so far. Read it fully before starting work.

## Working conventions (important)
- User runs **Windows 11**, laptop i5-1240P, 8 GB RAM, **Anaconda**, conda env **`aqi`** (Python 3.11), VS Code.
- Explain things in **simple words, step by step**; the user is learning. Give honest time estimates
  before long runs, and update if they change. Ask before anything slow or expensive.
- Never invent health or medical claims; every threshold/advice must trace to a source in
  `docs/health_advisory_reference.md`.
- Never tune anything on the test period. Always report the persistence baseline next to model scores.
- Commands for the user's terminal must be single lines (multi-line pastes broke before).
- **Always run Python in the `aqi` conda env, never the default Python 3.14.** `conda` is not on Claude's shell PATH, so
  use the full path: `"C:\Users\Vijay kumar G\.conda\envs\aqi\python.exe" script.py` (bash: `/c/Users/Vijay kumar G/.conda/envs/aqi/python.exe`).
  aqi has Python 3.11.17, pandas 3.0.6, requests 2.34.2 (checked 2026-10-14). Check an env's package versions before changing model code.
- **The user's VS Code terminal is PowerShell.** Give commands with the call operator before quoted paths, e.g.
  `& "C:\Users\Vijay kumar G\.conda\envs\aqi\python.exe" -m uvicorn backend.app:app --port 8000`, or plain `python ...` when the aqi env is
  active (prompt shows `(aqi)`). Do not use `&&` (not in Windows PowerShell 5.1); use `;`. Claude's own shell is Git Bash (POSIX paths).
- Before testing the website make sure no old `uvicorn` process is still running (stale servers served old code and gave wrong test results).
- Windows note: notebooks set `os.environ["LOKY_MAX_CPU_COUNT"]="8"` to silence a joblib `wmic` warning.
- Package downloads (pip) work on the user's PC. Data sources: OpenAQ / Open-Meteo are reachable from the
  user's PC.

- **Port 8000 is the user's own server: NEVER kill it, never use broad `*uvicorn*` kill commands.** Test servers use other ports
  (8011-8099; tests use 8025/8032/8033 etc.) and are stopped only by the PID that listens on that exact port. (Before 17 Oct 2026 some
  of my broad kill commands may have stopped the user's own server without telling them.)

## Folder layout
```
notebooks/   CSH_AQI_hybrid_forecasting.ipynb   main pipeline: raw 15-min data -> cleaning -> CPCB AQI -> CSH-AQI -> results
             CSH_AQI_on_your_hourly_data.ipynb  same model on the user's earlier processed hourly files (comparison only)
model/       aq_clean.py (cleaning + CPCB AQI), aq_model.py (features, CSH-AQI, baselines, metrics), run_final.py (script version)
data/raw/            8 raw OpenAQ/KSPCB 15-minute exports (CSV text; originally named .xls)
data/processed/      clean_hourly_all_stations.csv  (output of the cleaning step)
data/processed_user/ the user's earlier processed hourly files (gap-filled; use only for comparison)
results/     metrics (csv/xlsx) and figures from the final runs
docs/        health_advisory_reference.md (thresholds, advice, sources)
backend/ frontend/ alerts/   empty: real-time system goes here
```
Notebooks expect to be run from `notebooks/` (paths `../data/raw`, `../results`).

## Data
Stations (OpenAQ location_id, lat, lon):
| station | id | lat | lon | raw file |
|---|---|---|---|---|
| Silk Board, Bengaluru | 6975 | 12.917348 | 77.622813 | Merged_silkboard |
| Hebbal, Bengaluru | 6984 | 13.029152 | 77.585901 | Merged_hebbal |
| Jayanagar 5th Block, Bengaluru | 6973 | 12.920984 | 77.584908 | converted_jayanagar |
| Chikkaballapur Rural | 6954 | 13.428828 | 77.731418 | Merged_chikkaballapura |
| Kalyana Nagara, Chikkamagaluru | 10902 | 13.328028 | 75.797056 | Merged_chikkamagaluru |
| Hebbal 1st Stage, Mysuru | 7289 | 12.21041 | 76.37376 | Merged_mysuru |
| Vijay Nagar, Ramanagara | 10909 | 12.733409 | 77.298051 | Merged_ramanagara |
| Stuart Hill, Madikeri | 11582 | 12.415911 | 75.73505 | Merged_madikeri |

Raw columns: datetimeLocal, location_id, location_name, latitude, longitude, co, no, no2, nox, o3, pm10, pm25,
relativehumidity, so2, temperature, wind_direction, wind_speed (Chikkamagaluru has no wind). Feb 2025 – Aug 2026
(Ramanagara from Nov 2025). NOx is in ppm (others µg/m³; CO mg/m³), so it's not used in AQI.

Data quality problems found and handled in `aq_clean.py`:
- Error codes 999.99 / -99.99; PM ≤ 0; out-of-range met values -> NaN.
- Glitch pattern: PM2.5 ≈ 600–800 exactly when PM10 is missing -> rejected.
- Stuck sensor: same high value repeated ≥ 3 h (Madikeri 596/799) -> rejected.
- Hampel-style spike filter (3 h median, 7-day robust spread); PM2.5 > 1.5·PM10+20 rejected.
- Hourly mean needs ≥ 2 of 4 readings; only gaps ≤ 3 h interpolated; longer gaps stay NaN (never fill with averages).
- Lessons from the user's earlier pipeline: fillna(0) before averaging biased daily means low; mean-filling
  whole days created fake flat patterns; imputing before rolling averages defeated CPCB's 16-of-24 h rule.

## CPCB AQI (implemented exactly)
24 h running mean for PM2.5, PM10, NO2, SO2 (min 16 valid hours); 8 h for O3, CO (min 6). Sub-index by CPCB
breakpoints (top "Severe" band given a finite upper limit so AQI can exceed 400, capped 500). AQI = max sub-index,
valid only if ≥ 3 pollutants incl. PM2.5 or PM10. Categories: Good 0–50, Satisfactory 51–100, Moderate 101–200,
Poor 201–300, Very Poor 301–400, Severe 401–500. Dominant pollutant = argmax sub-index.

## The model: CSH-AQI (CPCB-Structured Hybrid)
Key idea: at forecast time t, most of each pollutant's CPCB averaging window ending at t+h is already measured
(e.g. h=6: 18 of 24 h known). Forecast only the unknown part, then rebuild AQI with the official formula.
- **Stage A**: per pollutant, gradient boosting predicts the mean concentration over hours t+1..t+h (8 h window
  pollutants: the unknown part of their 8 h window). Target log1p; anchored variant predicts log-ratio to the
  current 24 h mean.
- **Stage B** (no ML): combine known mean (K = W−h observed hours) and forecast mean -> running averages ->
  CPCB validity rule (observed + forecast hours ≥ 16/24 or 6/8) -> sub-indices -> AQI (max), dominant pollutant.
- **Stage C**: gradient boosting learns residual (true AQI − structural AQI), trained on out-of-fold
  (4 contiguous time blocks) Stage A predictions.
- **Direct GBM**: AQI directly; anchored variant predicts AQI(t+h) − AQI(t).
- **Final = equal-weight mean of 6 members**: Structural, Structural(anchored), Hybrid, Hybrid(anchored),
  Direct, Direct(anchored). Weights fixed a priori (not tuned).
- Learner: LightGBM if installed else sklearn HistGradientBoostingRegressor; 300 trees, lr 0.05, 31 leaves,
  min 40 samples/leaf, L2 1.0. 16 models per horizon, horizons 1, 6, 12, 24 h. One pooled model for all
  stations (station code is a feature).
- Features at t: pollutant values, lags (1,2,3,6,12,23 h), rolling means/std, CPCB averages and sub-indices,
  AQI lags (1..168 h) and changes, weather (temp, RH, wind speed, u/v) means, time (hour, dow, day-of-year
  sin/cos), target-hour time, "same window yesterday / same hour last week", known-part means and counts.
- Seasonal (day-of-year) features are dropped automatically if training covers < 330 days.
- Baselines: Persistence (AQI stays as now); "Huber+Huber 3h" = the user's previous best (two Huber
  regressions on the last 3 hours, averaged).

## Evaluation protocol
Calendar split (same as the user's earlier notebooks): train < 2026-04-17 07:00, validation 2026-04-17 07:00 –
2026-05-29 14:00, test 2026-05-29 14:00 – 2026-07-21 23:00, with an h-hour embargo at boundaries. Validation =
fit on train; Test = refit on train+validation, scored once. Metrics: MAE, RMSE, R², CPCB category accuracy,
alert F1 (AQI > 100). Scored only where true AQI is CPCB-valid.

## Results (OFFICIAL final run, 15 Oct 2026; test MAE; lower is better)
Source: `results/final/csh_metrics.csv`, `results/final/csh_run_info.json` (git commit 3539911, LightGBM 4.7.0, Python 3.11.17, pandas 3.0.6,
scikit-learn 1.9.1, 300 trees / 4 folds / lr 0.05, seeds 0/1, deterministic, input SHA-256 recorded; started 19:50, finished 21:08 IST).
Cleaned data, full history, same calendar split, test scored once. MAE / R2 / category accuracy / alert F1 (AQI > 100):
| horizon | persistence | Huber+Huber | CSH-AQI ensemble |
|---|---|---|---|
| +1 h | 1.089 / 0.988 / 0.980 / 0.966 | 1.083 / 0.987 / 0.982 / 0.965 | 0.653 / 0.994 / 0.987 / 0.982 |
| +6 h | 4.843 / 0.882 / 0.909 / 0.839 | 4.638 / 0.899 / 0.912 / 0.814 | 3.217 / 0.945 / 0.939 / 0.897 |
| +12 h | 7.126 / 0.808 / 0.864 / 0.708 | 6.985 / 0.821 / 0.873 / 0.705 | 5.322 / 0.892 / 0.900 / 0.793 |
| +24 h | 9.588 / 0.689 / 0.801 / 0.522 | 9.597 / 0.691 / 0.797 / 0.476 | 9.045 / 0.743 / 0.811 / 0.647 |
| +36 h | 11.648 / 0.556 / 0.769 / 0.476 | 11.959 / 0.557 / 0.755 / 0.394 | 11.060 / 0.649 / 0.757 / 0.603 |
| +48 h | 11.953 / 0.517 / 0.765 / 0.471 | 12.332 / 0.516 / 0.742 / 0.375 | 12.680 / 0.542 / 0.696 / 0.532 |
| +72 h | 13.130 / 0.440 / 0.728 / 0.292 | 13.459 / 0.463 / 0.700 / 0.244 | 13.713 / 0.473 / 0.654 / 0.455 |
- 1-24 h is the main result (CSH-AQI beats persistence and Huber at every horizon, both periods). 36 h: clearly better on MAE/R2/alert F1
  on validation, mixed on test (exact category worse than persistence). 48 and 72 h: NO MAE skill over persistence (report as tendency only).
- Reproduces the earlier 8 Oct run closely (0.647 / 3.222 / 5.303 / 9.022). Per-period accuracy tables: `results/accuracy/`.
- **Two comparison reruns, same official configuration** (`run_final.py`, FAST = False, LightGBM 4.7.0, 300 trees / 4 folds, run info in each
  folder; run by the user in their own terminal 15 Oct 22:18-23:25; `git_dirty: true` only because the result folders were untracked; code at
  commit 97812eb). They replace the older 8 Oct numbers (0.70 / 3.44 / 5.80 / 9.47 and 10.40 vs 9.69) in `results/CSH_AQI_results.xlsx`.
  **The datasets have different row counts, so compare models only within a dataset, never across datasets.**
  Test MAE / R2 / category accuracy / alert F1, n = evaluated rows:
  | dataset | h | n (test) | persistence | Huber+Huber | CSH-AQI ensemble |
  |---|---|---|---|---|---|
  | **Window** 1 Nov 2025 - 22 Jul 2026, cleaned data (`results/final_window/`) | 1 | 7638 | 1.089 / 0.988 / 0.980 / 0.966 | 1.131 / 0.985 / 0.982 / 0.968 | 0.704 / 0.994 / 0.987 / 0.986 |
  | | 6 | 7372 | 4.843 / 0.882 / 0.909 / 0.839 | 4.794 / 0.897 / 0.908 / 0.792 | 3.435 / 0.941 / 0.935 / 0.888 |
  | | 12 | 7078 | 7.126 / 0.808 / 0.864 / 0.708 | 7.310 / 0.814 / 0.864 / 0.653 | 5.835 / 0.873 / 0.890 / 0.771 |
  | | 24 | 6588 | 9.588 / 0.689 / 0.801 / 0.522 | 10.221 / 0.676 / 0.781 / 0.423 | 9.446 / 0.715 / 0.789 / 0.609 |
  | **Gap-filled** earlier hourly files (`results/final_user_files/`) | 1 | 10256 | 0.988 / 0.993 / 0.977 / 0.971 | 0.920 / 0.995 / 0.977 / 0.973 | 0.605 / 0.998 / 0.982 / 0.974 |
  | | 6 | 10256 | 4.509 / 0.899 / 0.894 / 0.855 | 4.157 / 0.917 / 0.906 / 0.872 | 3.184 / 0.949 / 0.927 / 0.890 |
  | | 12 | 10256 | 7.064 / 0.792 / 0.835 / 0.750 | 6.746 / 0.825 / 0.847 / 0.730 | 5.947 / 0.866 / 0.869 / 0.815 |
  | | 24 | 10247 | 9.927 / 0.635 / 0.767 / 0.573 | 9.691 / 0.675 / 0.779 / 0.511 | **10.487** / 0.660 / 0.753 / 0.714 |
  - Window: CSH-AQI beats persistence and Huber at every horizon on test MAE, but only narrowly at 24 h (9.446 vs 9.588; validation 12.987 vs 13.064,
    a tie), about 5-10% worse than the full-history model at 1-12 h (0.704 / 3.435 / 5.835 vs 0.653 / 3.217 / 5.322): less training history costs accuracy.
  - Gap-filled files: wins clearly at 1-12 h, but **loses at 24 h** to persistence and Huber on test (10.487 vs 9.927 / 9.691) and on validation
    (16.496 vs 15.113 / 14.102); winter-only training (no seasonal features) plus gap-filled values are the likely reasons (not tested). It also scores
    different, easier-to-fill rows (n = 10256 vs 7638), so its low 1 h MAE (0.605) must not be compared with the cleaned-data results.
  - Gap-filled lesson (as in the earlier pipeline notes): filling gaps before averaging hides missing data; the cleaned pipeline is the main result.
- Earlier finding: 1 h R2 ~ 0.99 is trivial (persistence already 0.988); always report skill vs persistence.
- Literature check: building pollutants-then-AQI isn't new; the observed+forecast CPCB-window decomposition appears new (not found). Claim
  carefully, "to our knowledge".

## Health advisory (see docs/health_advisory_reference.md for full tables and citations)
Sources: CPCB NAQI 2014; NCDC/MoHFW ASHA handbook 2024 (category-wise advice); NCDC Health Adaptation Plan 2021
(vulnerable groups, medicines, when to see a doctor); WHO 2024 Q&A on personal interventions (cautions).
- Vulnerable users (lung/heart disease, child < 14, older adult, pregnant, outdoor worker, athlete):
  advisory from AQI 51, alert from 101. Healthy adult: advisory from 101, alert from 201. Everyone alert ≥ 301.
  These thresholds are a design decision derived from the sources; state that.
- N95/N99 advice only from Very Poor (NCDC); show WHO cautions (no respirators designed for children; caution
  for heart/lung disease). Don't mention inhalers; say "keep prescribed medicines readily available".
- Always show the disclaimer (in the reference doc). Emergency number in India: 112.

## Data decisions for the live system (2026-10-14)
- Research/paper results stay on `data/raw` exactly as above; do not change them.
- Live model (step 2) trains on raw files before 1 Jul 2026 + OpenAQ S3 archive from 1 Jul 2026 onward
  (`backend/fetch_openaq_archive.py` -> `data/live/<id>_wide.csv`), and the archive part goes through the same `aq_clean.py` QC.
- Checked: archive matches raw exactly on the 1-26 Jul overlap (0 value differences); archive has extra values raw lacks and no duplicate timestamps.
- `data/archive_cache/` and `data/live/` are regenerable and git-ignored. Archive lags ~3 days; the OpenAQ v3 API (key pending) fills the latest hours.

## Build plan: real-time personalised alert system (NEXT)
User decisions: **local laptop only** (demo/viva); **browser pop-ups first, then email and WhatsApp**;
**profile saved in the browser** (localStorage, no login); frontend tech: any (keep it simple, HTML/JS fine).
Architecture: data updater (hourly) -> SQLite DB -> forecaster (hourly, CSH-AQI, horizons 1..24) ->
FastAPI backend -> website (profile, nearest station, 24 h chart, best-time planner, personal advice) ->
notifier (Web Notifications/push; later email via Gmail app password; WhatsApp via Twilio sandbox or Telegram).
Steps:
1. Data pipeline: history from the OpenAQ S3 archive (`s3://openaq-data-archive/records/csv.gz/locationid=<id>/year=YYYY/month=MM/location-<id>-YYYYMMDD.csv.gz`, no key,
   `--no-sign-request`, region us-east-1; long format -> pivot to wide like data/raw) + live data from the OpenAQ v3 API
   (free key, header `X-API-Key`, `/v3/sensors/{id}/hours`) + hourly weather from Open-Meteo (archive + forecast).
   Verify formats on first fetch; don't assume.
2. Retrain CSH-AQI on all data (+ weather features), lighter live version for horizons 1..24, save models (joblib).
3. Backend: APScheduler hourly update + forecast; FastAPI endpoints (stations, forecast, advice).
4. Website: profile form (station or location, health group, activity, thresholds), dashboard, advice with
   source references, disclaimer.
5. Notifications: browser first, then email, WhatsApp.
6. Live evaluation for a few weeks (real forecast accuracy, alert counts) for the paper.
Real-time caveats: ~1 h data latency, station outages (fall back to persistence/nearest station with a warning).

## Optional research extras (not yet done)
Diebold–Mariano test vs baselines; error during AQI > 100 episodes; SHAP feature importance; leave-one-station-out
test; quantile models for exceedance probabilities; WHO/AirQ+ PM2.5 health-impact estimates;
Open-Meteo "Previous Runs" API (weather at fixed lead times, e.g. forecast issued 1 day earlier) so that training weather
matches the lead time of live 12-24 h forecasts.

## OpenAQ API / archive findings (2026-10-14)
- Key is in `.env` (git-ignored). Free tier: 60 requests/min. `backend/fetch_openaq_api.py` reads hourly values (`/v3/sensors/{id}/hours`)
  for the same sensor ids as the S3 archive (locations list duplicate sensors per pollutant; use the archive's). Data reaches ~now.
- **Hour convention differs:** API hour value labelled `To` = mean of readings in (To-1h, To] (verified vs archive 15-min data, MAE ~0.01).
  `aq_clean.py` uses `resample("1h")` = readings in [h, h+1h) labelled by the start. API hourly values must NOT be mixed directly into
  aq_clean output (1 reading / 15 min shift). Plan: fetch the live tail as 15-min `/measurements` and run it through aq_clean unchanged.
- **Unit labels:** archive/API label co, no, no2, so2 as "ppb" (o3, pm as ug/m3). Values are identical to `data/raw`, which this project
  treats as ug/m3 (CO mg/m3) as CPCB publishes. Physical sanity check: CO ~0.9 as ppb would be impossible for a city, so the "ppb"
  label is almost certainly wrong. Inference, not proof: the ug/m3 twin sensors are inactive. Verify one hour against CPCB's CAAQMS site.

## Live data findings and pipeline (2026-10-14)
- **Latency:** at 22:09 IST on 14 Oct the newest API reading at 5 stations was 13 Oct 23:30 (~22.5 h old); all stations end at 23:30 or
  earlier, nothing from 14 Oct. Looks like a daily batch upload (one snapshot only; re-check after midnight). Real-time (1 h) alerts are NOT
  possible with OpenAQ/KSPCB data as it stands; the S3 archive lags ~3 days.
- **UPDATE 17 Oct 2026 10:10 IST - the feed is STALLED, not a daily batch:** nothing newer than 13 Oct 23:30 has arrived at any station in the 3.4 days since.
  Newest reading / age: Silk Board, Hebbal, Jayanagar, Mysuru, Madikeri 13 Oct 23:30 = 82.7 h (3.4 days); Ramanagara 13 Oct 19:15 = 86.9 h (3.6 days);
  Chikkaballapur 13 Oct 13:00 = 93.2 h (3.9 days); Chikkamagaluru 12 Oct 10:00 = 120.2 h (5.0 days). The S3 archive's newest day file is also 13 Oct
  (checked for Silk Board, Mysuru, Madikeri), so it is not a delay in one OpenAQ path. Age of the newest reading at each check: 22.5 h (14 Oct 22:09), 44 h
  (15 Oct 19:29), 58 h (16 Oct 09:45), 82.7 h (17 Oct 10:10). Consequence: every live e-mail alert is paused (the rule needs data < 12 h old); only the daily
  "data feed stopped" notice applies; live mode shows the red "DATA IS OLD" banner. `update_all.py --quick` was NOT run (nothing new to fetch).
  Root cause is upstream (KSPCB -> CPCB -> OpenAQ ingestion) and unknown; data.gov.in was down and WAQI stale for the same stations since 23 Jun.
- **API fetcher** now uses 15-min `/v3/sensors/{id}/measurements` (matches archive exactly: 0 value differences). A full 8-station update
  is 96 calls (12 sensors x 8) and takes ~2-4 min at 60 calls/min. Tail from 8 Oct is the same call count (one page per sensor).
- **Sensor outages in recent data:** Ramanagara no/no2/nox none since 1 Jul 2026 (harmless: AQI was 99% valid in Sep without NO2; its AQI is invalid in Oct because only 32% of Oct hours have ANY data - a whole-station outage, newest valid AQI 8 Oct); Hebbal no/nox since 6 Aug;
  Jayanagar and Chikkaballapura wind_speed none since 1 Jul; Chikkamagaluru has no wind. Chikkaballapura API data ends 13 Oct 13:00,
  Chikkamagaluru 12 Oct 10:00.
- **Weather features (decision):** keep station sensor weather as features and ADD Open-Meteo as extra features (do not replace).
- **Pipeline:** `backend/build_dataset.py` stitches raw (<1 Jul 2026) + archive (>=1 Jul) + API tail -> `data/live/combined/` (raw format) ->
  `aq_clean.build_clean_dataset` unchanged -> SQLite `data/aqi.db` (tables `hourly`, `weather_hist`, `weather_fcst`; git-ignored).

## Decisions 2026-10-14 (latency) and open investigation
- Do both: (1) live daily outlook with horizons up to ~72 h from the last observation, evaluated on the same calendar split and reported
  separately from the 1-24 h research results, with persistence baseline; (2) investigate near-real-time sources.
- **Replay mode** is the main viva demo: backend/website runs over a past period (default: test period 29 May - 21 Jul 2026) hour by hour using
  only data available at each simulated hour, with a clear "Replay" label.
- Near-real-time sources (web search only, nothing built; page fetch of data.gov.in returned 403 so unverified):
  data.gov.in CPCB "Real time Air Quality Index from various locations" lists granularity hourly, but its page says "API for this resource does
  not exist / use Request API"; third-party tutorials show resource id 3b01bcb8-0b14-4abf-b6f2-c1bfd384ba69 (may be outdated); station coverage
  of our 8 KSPCB stations and licence NOT verified. WAQI/aqicn lists Silk Board (id @11293, data credited to CPCB); needs free token; terms not checked.
  CPCB CAAQMS portal (airquality.cpcb.gov.in) is often unresponsive per CEEW; no documented API/terms found.
- `backend/update_all.py` = one command (archive -> API -> weather -> build). `backend/check_latency.py` = how old is the newest reading.

## Long horizons (36/48/72 h) - checks and first result (2026-10-14)
- **Bug found and fixed** (`aq_model.py`): for h > 24 the "same window yesterday" features (`*_win_yday`) used `shift(24-h)` = negative shift =
  FUTURE data (leak). Now `day_lag = 24*ceil(h/24) - h` (>= 0; identical for h <= 24, so research results for 1-24 h are unchanged).
  Proven with `model/test_no_leakage.py` (features at t must not change when data after t is removed): leaked at h=36/48/72, none after fix.
- **K <= 0 structural path** checked with `model/test_structural_oracle.py` (feed true future window means -> must give true AQI): MAE 1.45
  for h=24,36,48,72 (0.8 at h=6), so the fully-in-the-future window is handled; the small residual is inherited from the 75%-completeness
  target rule / gap-filled hours and was not diagnosed further.
- **Timing:** one horizon = 7.4 min (val 3.5 + test 3.9) on the laptop. First long-horizon result, h=48 (test, never tuned):
  persistence MAE 11.95 R2 0.517; Huber 12.33 / 0.516; CSH-AQI ensemble 12.65 / 0.545; best member Direct GBM anchored 12.24 / 0.570.
  => at 48 h the model has NO MAE skill over persistence (R2 slightly better). Report honestly; results in `results/long_horizon/`.

## Long-horizon results (36/48/72 h) and oracle diagnosis (2026-10-14) - report SEPARATELY from the 1-24 h results
Same calendar split, nothing tuned on test, same rows for every model (n = 4583 / 4820 / 4647 test rows; fewer than the 1-24 h tables because the
last-week baseline needs 168 h of history). `results/long_horizon/long_horizon_table.csv`, built by `model/long_horizon_table.py`.
Test MAE / R2 / category accuracy / alert F1 (AQI>100):
| h | persistence | same hour 2/3 days ago | Huber+Huber | CSH-AQI ensemble | best member (Direct GBM anch.) |
|---|---|---|---|---|---|
| 36 | 11.36 / 0.541 / 0.759 / 0.466 | 11.43 / 0.536 / 0.758 / 0.482 | 11.68 / 0.552 / 0.741 / 0.287 | 11.46 / 0.608 / 0.732 / 0.586 | 11.04 / 0.633 / 0.738 / 0.552 |
| 48 | 11.62 / 0.507 / 0.753 / 0.468 | = persistence (h multiple of 24) | 11.97 / 0.514 / 0.726 / 0.318 | 13.21 / 0.470 / 0.676 / 0.512 | 12.52 / 0.517 / 0.693 / 0.480 |
| 72 | 12.87 / 0.433 / 0.723 / 0.355 | = persistence | 12.98 / 0.487 / 0.694 / 0.234 | 13.85 / 0.412 / 0.652 / 0.414 | 13.33 / 0.462 / 0.674 / 0.267 |
- Honest reading: beyond 24 h the ensemble has NO MAE skill over persistence at 48/72 h (worse on test) and about none at 36 h (better RMSE,
  R2 and alert F1). Validation at 36 h was clearly better (MAE 14.7 vs 18.4); 48/72 h validation also shows no gain. The test period is a
  low-AQI monsoon stretch, so differences are small in absolute terms. Same-hour-last-week is worse than persistence everywhere.
- **Framing decision:** the live outlook beyond 24 h is shown as category + trend with a "lower confidence" label. 1-12 h is the main result.
- **Oracle diagnosis (why MAE 1.45, not ~0):** at h=24 (K=0) ALL error > 1 comes from rows where CPCB's running average exists (>= 16 of 24 valid
  hours) but the Stage-A target requires >= 18 of 24 (75%), so the reconstructed average is NaN and the AQI is built from fewer pollutants.
  Excluding those rows MAE = 0.25 = pure rounding of the true AQI. At h=6 the residual (MAE 0.82) comes from gaps in the observed part:
  (K*known_mean + L*forecast_mean)/W assumes a complete window; rows with a complete observed part reconstruct within rounding 98.7% of
  the time (MAE 0.52), rows with gaps 71% (MAE 1.63). Evaluation is against the official AQI, so this cannot inflate any reported result; it only
  costs the structural member a little accuracy (<= ~1.4 AQI points in the oracle vs forecast errors 3-9). Possible later improvement (would
  change research numbers, so not done): weight by valid-hour counts and use a 16-of-24 target rule.

## Near-real-time source investigation, step 1 (2026-10-14; no long runs; recommendation pending user OK)
| source | our 8 stations | latency | gives | resolution | limits | terms (student use) | status |
|---|---|---|---|---|---|---|---|
| OpenAQ v3 (have) | all 8 | measured ~23 h (daily batch ending 23:30); archive ~3 d | concentrations | 15 min | 60 req/min | open data, key | working |
| WAQI / aqicn | Silk Board (@11293) known; other 7 NOT verified | NOT measured (token needed: .env `WAQI_TOKEN=`) | AQI sub-indices (US-EPA style), not concentrations | ~hourly (per site) | 1000 req/s | free API; attribution mandatory; non-profit public use needs email notice; data "can not be redistributed as cached or archived data", not for paid apps | needs token |
| data.gov.in CPCB real-time AQI | NOT verified | NOT measured; endpoint answers 400 "Authorization field missing" without key; page says API "does not exist/Request API" | AQI by station (fields unverified) | hourly (per page) | unknown | Govt open data licence not confirmed | needs key |
| CPCB CCR portal (airquality.cpcb.gov.in/ccr/) | NOT checked | NOT measured | dashboard (JS), no documented API | - | - | no terms/API docs found on page; robots.txt absent (404). NOT scraped | do not use |
| Open-Meteo Air Quality (CAMS) | all 8 (grid ~0.1 deg, model) | none (model analysis/forecast, incl. current hour) | concentrations pm2_5,pm10,NO2,SO2,O3,CO (ug/m3; CO /1000 -> mg/m3) | hourly | free non-commercial | free, no key | tested |
| IQAir AirVisual | station data only on paid tiers | - | - | - | free: 5/min, 500/day, city-level only | - | not feasible |
- CAMS vs our station hourly data, 1 Jul-13 Oct 2026, correlation r per station: PM2.5 0.05-0.77 (median ~0.6), PM10 0.14-0.70, NO2 -0.12-0.57,
  O3 -0.17-0.72, SO2 -0.37-0.45, CO -0.01-0.62. Mean bias (CAMS - station): PM10 -38, PM2.5 -8, O3 +32, NO2 -2, SO2 -6 ug/m3, CO -0.27 mg/m3.
  Hour label alignment could not be determined (best shift -1/0/+1 mixed, correlations weak). => usable only as weak extra features /
  gap indicator, NOT a replacement for station data.

## WAQI test result (2026-10-14) - WAQI is NOT usable for our stations right now
- Coverage: all 8 stations exist in WAQI (uids: Silk Board 11293, Hebbal 11428, Jayanagar 11276, Chikkaballapur Rural 11316, Kalyana Nagara
  Chikkamagaluru 12811, Hebbal 1st Stage Mysuru 12439, Vijay Nagar Ramanagara 12426, Stuart Hill Madikeri 13719).
- Latency: ALL 8 (and every Bengaluru/Karnataka KSPCB station found, 15 in total) have newest reading 2026-06-23 10:00 IST, i.e. 113 days
  stale, aqi "-". WAQI itself is alive (Delhi CPCB stations 0.3 h old; of 91 Indian stations checked 13 were < 6 h, 69 > 30 days stale).
  So the Karnataka KSPCB feed into WAQI stopped on 23 Jun 2026. OpenAQ still receives data for the same stations (different path).
- Conversion test (single frozen 23 Jun snapshot vs our raw data, n=6-7 stations, weak statistics): WAQI iaqi are US-EPA sub-indices (not
  CPCB). PM2.5 inverts to concentration within ~2.5 ug/m3 using the OLD EPA table (12.0 ug/m3 breakpoint); the 2024 table (9.0) is ~3-5 too low.
  PM10 within ~10 ug/m3 (instantaneous/NowCast vs our reading). Gases (NO2, SO2, O3, CO) are consistent with EPA indices of the same physical
  values (ppb/ppm), so they can be inverted to ug/m3 (factors assume 25 C). BUT CPCB AQI needs 24 h / 8 h running means; WAQI gives one
  value per pollutant per hour, and building the 24 h mean would need archiving 24 snapshots, which WAQI terms forbid. So at best an
  instantaneous CPCB-style estimate, labelled "estimated, not official CPCB AQI". Never show WAQI AQI as CPCB AQI.
- Terms respected: no WAQI values stored in the repo or in files; attribution required if shown. Decision: keep a WAQI freshness guard
  (use only if the newest reading is < 6 h old) so it activates automatically if KSPCB feeds resume; otherwise fallback = OpenAQ + persistence.
- data.gov.in key not yet tested (no key). It is likely stale too if CPCB's feed to WAQI is the same upstream; unverified.

## data.gov.in test result (2026-10-14) - no usable data; do not build on it
- Key in `.env` (`DATA_GOV_IN_API_KEY`). `GET https://api.data.gov.in/resource/3b01bcb8-0b14-4abf-b6f2-c1bfd384ba69` returned a read
  timeout (60 s) then HTTP 502 after ~61 s on three attempts (plain query and `filters[state]=Karnataka&limit=5`), while the data.gov.in
  portal itself answered 200. The key was accepted by the gateway (no 401/403) but the backend never produced data. Consistent with the
  resource page saying "API for this resource does not exist / Request API" and with CEEW's report that the service is often unresponsive.
- Coverage, latency, fields, units, rate limits and licence therefore could NOT be established. Retry any time with
  `backend/check_datagovin.py` (single call); if it ever answers, check Karnataka station names and `last_update` first.
- Net result of all near-real-time tests: OpenAQ (~23 h batch) remains the only working source for our 8 stations. WAQI stale since
  23 Jun 2026, data.gov.in down, CPCB CCR has no documented API (not scraped), CAMS is a model (weak features only).
- **Replay design note:** the research test predictions (`results/csh_aqi_predictions_full_history.pkl`, horizons 1/6/12/24, `datetime` =
  forecast origin t, `y` = true AQI at t+h, models fit before the test start with an embargo; features proven causal by
  `model/test_no_leakage.py`) and `results/long_horizon/*_preds.pkl` (36/48/72 h) can drive replay mode without retraining.

## Replay mode + website (built 2026-10-15)
- Period event counts (true AQI, valid hours): validation (17 Apr-29 May) has 1393 h > 100 and 42 h > 200 (Silk Board 560/28, Hebbal 355/14,
  Jayanagar 342/0, Chikkaballapura 69, Mysuru 57/0); test (29 May-21 Jul) has 308 h > 100 (306 at Silk Board, 2 at Chikkamagaluru) and ZERO > 200.
  => Replay defaults to the validation period (fit on train only, equally out-of-sample); the test period stays selectable. Validation was
  used for design decisions in the research phase, so the TEST period remains the official scored result; replay is a demonstration.
- `backend/make_replay_data.py` -> `data/replay.db` (git-ignored; needs the prediction pickles in results/). No retraining.
- `backend/app.py` (FastAPI) + `backend/advice.py` (messages quoted from docs/health_advisory_reference.md, with source numbers) +
  `frontend/` (index.html, app.js, style.css, vendored Chart.js 4.4.1, no CDN needed). Run from the project root:
  `"C:\Users\Vijay kumar G\.conda\envs\aqi\python.exe" -m uvicorn backend.app:app --port 8000` then open http://127.0.0.1:8000
- Causality: /api/replay/state returns observed hours <= T, forecasts whose origin is exactly T, and true values only for targets that
  have already happened (checked). Times are shown as hour-ENDING (aq_clean labels hours by their start).
- Discrete horizons are shown and labelled (+1, +6, +12, +24 main; +36, +48, +72 lower confidence). Hours in between are not interpolated.
  Optional later improvement: extra horizons (2, 3, 9, 18 h) so the 1-24 h chart is denser (needs retraining, ~7 min per horizon).
- Known replay limitation: forecast rows exist only where the true AQI later turned out valid (research evaluation mask), so a few hours
  with data gaps show "no forecast"; a live system would also forecast through gaps.
- Notifications: Web Notifications API (permission via button) plus in-page toast, fired when the highest <= 24 h forecast reaches the
  user's alert level (rising edge, 5-point hysteresis). Demo profile = lung disease, alert from 101. Users may lower, never raise, thresholds
  (enforced in both the page and /api/advice).

## Accuracy report per horizon (2026-10-15; `model/accuracy_report.py`, `results/accuracy/*.csv`; no retraining or tuning)
- Source: saved out-of-sample predictions (data/replay.db), CPCB-valid targets only, same rows for CSH-AQI and persistence.
- **Discrepancy to resolve:** the saved `results/csh_aqi_results_full_history.csv` and the prediction pickle agree with each other and give test
  MAE 0.662 / 3.286 / 5.304 / 8.873 and R2 0.994 / 0.943 / 0.891 / 0.751 (1/6/12/24 h). The "Results" table above in this file says
  0.65 / 3.22 / 5.30 / 9.02 and R2 0.945 / 0.743 at 6/24 h, i.e. from another run. Before the paper, decide which run is final and make this file match.
- Test: CSH-AQI beats persistence on MAE and exact category at 1-24 h (e.g. 24 h MAE 8.87 vs 9.59, category 81.5% vs 80.1%), but at 36-72 h
  persistence has the better exact-category accuracy (36 h 76.9 vs 75.6; 48 h 76.5 vs 69.9; 72 h 72.8 vs 65.4) and at 48/72 h better MAE.
  Within-+-1-category accuracy is 99.8-100% for both models (uninformative: the test period is mostly Good/Satisfactory).
- Error ranges: validation signed-error quantiles per horizon cover 87-90% (80% interval) and 93-96% (90% interval) of test errors, but for
  forecasts >= 100 at 24-72 h the 80% interval covers only 54-66% of test errors (small n, mostly Silk Board): ranges are too narrow exactly where
  alerts matter. For deployment recompute quantiles from validation+test pooled (both out-of-sample) and widen the upper tail at high AQI.
- Confidence tiers (by EFFECTIVE horizon = data age + lead time): high 1-6 h, medium 12-24 h, low 36-72 h ("tendency only").

## Results provenance and the official final run (2026-10-15)
- **Two result sets exist.** (a) `results/CSH_AQI_results.xlsx` (file created 8 Oct 2026) holds the numbers in the "Results" table above
  (test MAE 0.647 / 3.222 / 5.303 / 9.022). (b) `results/csh_aqi_results_full_history.csv`, `csh_aqi_predictions_full_history.pkl`,
  `CSH_AQI_metrics_by_horizon_full_history.xlsx` (files created 14 Oct 2026 15:04) give 0.662 / 3.286 / 5.304 / 8.873. Persistence is
  identical in both (same rows). (b) is slightly worse at 1-6 h, which is what a lighter configuration (notebook `FAST = True`: 60 trees,
  lr 0.15, 2 folds) would do, so (b) is probably a FAST smoke-test run. NOT proven: the notebook has no stored outputs and there is no log.
- Consequence: replay (1-24 h), the accuracy tables and the range quantiles currently rest on set (b); 36/48/72 h come from non-FAST
  LightGBM runs (300 trees, 4 folds, aqi env, 15 Oct). The set is inconsistent until the official run below replaces it.
- **Environment (aqi):** Python 3.11.17, numpy 2.4.6, pandas 3.0.6, scikit-learn 1.9.1, scipy 1.17.1, LightGBM 4.7.0 (used automatically).
- **Smoke test confirmed by the user (15 Oct):** the 14 Oct 15:04 files were produced with `FAST = True` (run ~20:30 IST 14 Oct); they are
  moved to `results/smoke_test_FAST_2026-10-14/` and must not be quoted.
- **Official final run (DONE 15 Oct 2026, 19:50-21:08 IST, 78 min; ~11.7 min per horizon, slower than the 7.4 min measured before
  `deterministic=True, force_row_wise=True`):** `model/run_final.py` on `data/processed/clean_hourly_all_stations.csv`, horizons
  1,6,12,24,36,48,72, 300 trees / 4 folds / lr 0.05 / 31 leaves (no FAST mode in run_final.py), seeds 0 (stage A, direct) and 1 (stage C),
  LightGBM `deterministic=True, force_row_wise=True`. It writes `<prefix>_run_info.json` (versions, git commit, input SHA-256, settings, times).
  Its numbers ARE the paper results; regenerated from it:  `data/replay.db` (make_replay_data.py), accuracy tables (accuracy_report.py),
  ranges (make_quantiles.py) and update this file. 
- **Range rule (website):** `model/make_quantiles.py`; pooled validation+test quantiles per horizon and forecast band (low <60, mid 60-100,
  high >=100), high-band upper end = 95th pct. Paper version = fitted on validation, checked on test (`results/accuracy/range_rule_val_to_test.csv`):
  overall coverage 82-87% (nominal 80%) but only 57-66% in the high band at 24-72 h. Confidence tiers: high <= 6 h, moderate 12-24 h,
  low >= 36 h, based on EFFECTIVE horizon = data age + lead time.

## Two-level alert and its test-period performance (2026-10-15; `model/alert_levels.py`, `results/accuracy/alert_levels.csv`)
- Likely = forecast >= user's threshold; Possible = forecast below it but upper end of the likely range >= threshold. Ranges for the test period
  fitted on validation only. Event = actual AQI >= threshold at the target hour.
- Test period, threshold 101 (308 event hours, 11 event onsets at 1 h; 306 of the hours are Silk Board): hit rate Likely / Likely+Possible,
  false alarms as % of alerts Likely / Likely+Possible: 1 h 96% / 100%, 0.7% / 4.6%; 6 h 91% / 98%, 12% / 38%; 12 h 83% / 98%, 23% / 54%;
  24 h 78% / 99%, 44% / 63%; 36 h 65% / 99%, 46% / 65%; 48 h 67% / 99%, 59% / 66%; 72 h 56% / 99%, 68% / 65%.
  "Possible" adds 20-40 points of hit rate but most Possible alerts are false alarms (precision 15-40%).
- Event ONSETS (first hour of an event) are caught much less often by Likely alone (18-64%); Likely+Possible 70-100%.
- Test period, threshold 201: zero events, so hit rate is undefined; Possible alerts at 12/24/48/72 h (21/18/114/526) were all false alarms.
  Validation (42 events > 200, ranges in-sample): Likely catches 88% at 1 h, 43% at 6 h, 12% at 12 h and 0% at 24+ h.
- Interpretation: beyond ~12 h the two-level alert is a heads-up that trades many false alarms for coverage; present it with the confidence tier.

## Minimal live mode (built 2026-10-16)
- Data state when built: OpenAQ newest reading still 13 Oct 23:30 at 5 stations (58 h old at 09:45 IST on 16 Oct); Chikkaballapur/Chikkamagaluru/
  Ramanagara older. All stations show a red "DATA IS OLD" banner (severity: fresh <= 3 h, delayed <= 24 h, stale > 24 h).
- Pipeline: `update_all.py` (archive -> API -> weather -> `build_dataset.py` -> `forecast_live.py`). `forecast_live.py` writes table `live_forecast`
  in data/aqi.db from each station's newest valid-AQI hour (no forecast if none in 7 days). If `models/live/h<h>.joblib` exists it uses the 6-member
  CSH-AQI ensemble (`backend/live_model.py`, trained by `backend/train_live.py`, ~6 min per horizon, 7 horizons ~45 min, NOT yet run), otherwise the
  PERSISTENCE FALLBACK (forecast = last observed AQI), always labelled "Persistence fallback" with a warning. A failed fetch step keeps the old
  database, so the page just shows older data with the age banner.
- API `backend/live_api.py`: `/api/live/stations`, `/api/live/state?station=`. Every forecast is labelled by its EFFECTIVE horizon (hours after the
  newest observation) and by "relative to now"; horizons whose target time has already passed are flagged "past" (nothing to check them against
  yet). Confidence tier from the effective horizon (<= 6 h high, <= 24 h moderate, else low = tendency only). Persistence ranges come from
  `persistence_ranges` in `backend/ranges.json` (same rule as the model ranges, errors of the persistence forecast).
- Page `frontend/live.html` + `live.js` (link from the replay page): chart in hours after the last observation with an orange line at the real
  "now", observed line broken at data gaps, table, advice (uses the profile from the replay page), no pop-ups (alerts by e-mail later).
- With stale data only the +72 h horizon (and nothing else) lies in the future, so live forecasts are tendencies; with persistence they are
  just the last AQI. 1-12 h skill is only usable once a fresher data source exists.

## Bug fixes from the user's first real use (2026-10-16)
- **E-mail rate limit race (serious):** five [REPLAY DEMO] e-mails went out within ~2 min although the limit was 1 per 60 s (log: gaps 19/56/6/24 s).
  Cause: the send time was recorded only AFTER the 2-3 s SMTP call, so requests arriving during that window (fast replay) all passed the check
  (reproduced: 6 simultaneous requests -> 6 sends; sequential requests were limited correctly). Fix: `notify_email.reserve_replay_slot()` reserves the
  slot under a lock BEFORE sending, in REAL time, persisted in `data/replay_mail_rate.json` (survives restarts; consumed even if the send fails);
  `429` with a `Retry-After` header. Regression test `backend/test_email_rate_limit.py` (synthetic-clock rules, 8-thread race, and the real
  HTTP endpoint with a slow fake send: exactly 1 of 6 simultaneous requests sends); test env vars `AQI_EMAIL_FAKE`, `AQI_RATE_FILE`,
  `AQI_PROFILE_FILE`, `AQI_MAIL_MIN_GAP_S`, `AQI_MAIL_PER_HOUR`. The page retries a rate-limited e-mail once, only if that alert is still on screen.
  `notify_email` no longer imports `app` a second time (it uses the already loaded module).
- **Escalation:** a higher level (possible -> likely) or a HIGHER CATEGORY than the last alert for the station now replaces the on-screen alert and
  bypasses the 12 h cooldown (and sends a new e-mail with subject prefix "UPDATE, higher category"). Case found: 24 Apr 2026 02:00 Silk Board observed
  250 (Poor) while the pop-up still showed 187 (Moderate). Headless test from 23 Apr 17:00: alerts 163 Moderate -> 201 Poor (replaced) -> 248 Poor,
  0 violations (the self-test now fails if an alert is lower in category than the highest <= 24 h likely forecast). General runs: 1 h/step x150 -> 8
  pop-ups, 3 h/step x80 -> 16 pop-ups (1 escalation), max 1 at a time, 0 violations.
- **One notification channel:** with browser notifications enabled only the system notification is shown; otherwise the small in-page pop-up.
- Forecast table headers no longer wrap mid-word; the "Your alert" column says "Likely level (not notified)" / "Possible level (not notified)" outside the
  notification rules (likely > 24 h, possible > 12 h).
- Live page: a low-confidence (> 24 h) or stale-data forecast is described as "Tendency only, not an alert"; with data > 12 h old the advice card is grey,
  titled "Last known conditions" and based on the last observation; footer says "E-mail alerts are paused while data is older than 12 h."
  (switches to "active while the data is fresher than 12 h" when fresh).

- **Escalation e-mails were dropped by the rate limit (2026-10-16, second report):** at 6 h/s through the 24 Apr Silk Board spike only Moderate e-mails
  arrived. The Poor request hit the 60 s limit (429) and the page's single retry was skipped because the pop-up had been replaced. FIX: a server-side
  OUTBOX (`notify_email.ReplayOutbox`): the endpoint QUEUES the e-mail (composed on the server at alert time); a worker sends one whenever a real-time
  rate-limit slot is free, highest priority first (escalation, then CPCB category, then level, then AQI), even if the pop-up has been replaced. A pending
  e-mail is superseded only by a newer one for the same station with a higher category, or the same category and level (then the newest wins); a lower
  category is not queued behind a pending higher one; pending e-mails expire after 30 real minutes; max 20 pending. `GET /api/email/outbox` shows
  fake flag, pending/sent/dropped subjects and a timestamped event log. The page's own retry timer was removed.
- **Client race found by the end-to-end test:** the page read the simulated hour AFTER an `await`, so e-mails were composed for a later hour than the
  alert (e.g. an alert from 13:00 produced an e-mail "for 19:00"). Now hour, period and station are captured when the alert is raised.
- **End-to-end result** (headless Chrome, 6 h/step, 23 Apr 00:00 -> 26 Apr 06:00, e-mail box ticked, sending faked, gap 3 s): 7 alerts -> 7 e-mails queued
  within 0.4 s -> sent: 116 Moderate at once, then (after the gap) 280 Poor; superseded: 130, 253 (Poor, replaced by the newer 280 Poor), 147, 109, 186.
  Poor e-mail arrives; 0 failures; playback 7 pop-ups, 0 violations.
- **MISTAKE to avoid (my test runs sent 11 REAL e-mails, 16 Oct 19:55-20:01 IST, to ALERT_EMAIL_TO):** the fake-send guard I added to `send()` did not
  apply (the text replacement silently did not match), so the test server used real SMTP because `.env` holds real credentials. Fixed: `send()` returns
  immediately when `AQI_EMAIL_FAKE=1`; `test_email_rate_limit.py` (Z1/Z2) replaces SMTP with a class that raises and checks `send()` never touches
  it; `/api/email/outbox` reports `fake`, and end-to-end scripts must abort unless it is true and must check that `data/email_log.jsonl` did not grow
  (verified 22 -> 22). Lesson: after any scripted text patch, grep to confirm the change exists before running anything that can send e-mail.
- `backend/test_email_rate_limit.py` now has 17 checks (Z safety, A rules, B race, C outbox priority/supersede, D HTTP queue); all pass.

- **Banner / slider / card drifting apart at 6 h/s (user recording, 2026-10-16):** banner "18 Apr 21:00" while the card said "data up to 23 Apr 03:00".
  Cause: timer-driven playback fired a new request every second whether or not the last had answered, the slider moved BEFORE its data arrived, and the
  alert/advice step used a second round trip that could belong to an older response. Fix: ONE request -> ONE response -> ONE synchronous `render()` per
  tick. `/api/replay/state` now also returns the advice (`groups`, `alert_from` as query parameters; basis = higher of now and the next-24 h forecast), so
  banner, slider (set from the displayed response, not the request), station card, chart, tables, advice and the alert decision all come from the same
  response. Playback is a sequential loop (next tick starts only after the previous one is displayed; a slow server just slows playback). Responses that
  are no longer the newest request are dropped completely. A user drag leaves the slider thumb where the hand put it (`sliderPending`) until the
  response for that position is displayed.
- **Consistency test (headless Chrome):** `?selftest=play&speed=S&seconds=N&latency=MS&scrub=0|1[&start=...]` runs the REAL playback loop with random
  response delays (out-of-order responses) and an emulated user dragging the slider, and after every render and every 200 ms checks that banner text,
  station card, slider position, chart, first table row, `data-stamp` stamps on all components and the alert time all show the same simulated hour; it
  also corrupts the banner on purpose to prove the check can fail. Results (Silk Board, validation, from 18 Apr): 1 h/s and 6 h/s, with no delay,
  with delays up to 2.5 s, and with slider dragging: 7 configurations, 0 violations; up to 23 responses dropped as out of order; no backwards jumps
  without scrubbing. (First version of this test reported violations only because `scrub=0` was parsed as true and because a user drag legitimately
  moves the thumb first; both handled.)
- **E-mail wording:** subject says "UPDATE, higher category" only when the CPCB category rose, and "UPDATE, higher alert level" when it went from
  possible to likely within the same category (page pop-up uses the same wording; the page sends `escalation: "category" | "level"`). Tests E1-E3 in
  `backend/test_email_rate_limit.py` (now 20 checks, all pass).

## Alert pop-up lifecycle in replay: pause-on-alert and 10 s minimum (user request, 17 Oct 2026)
- **Problem:** at 1 h/s a +1 h alert disappeared after ~1 s because its target hour passed in simulated time, so it could not be read.
- **Pause on alert** (Settings -> "Pause the replay when an alert is raised", ON by default, stored in localStorage `aqiPauseOnAlert`; developer switch
  `?pauseonalert=0|1`): raising an alert or an escalation STOPS the replay clock and the pop-up has two buttons, "Continue replay" (removes it and restarts the
  clock) and "Dismiss" (removes it, replay stays paused). The pop-up is pinned: it stays until a button is pressed (it is marked "(target hour now passed)" if
  the user steps forward). Pressing Play while it is up counts as continuing (unpinned, normal rules). With pause on, the in-page pop-up is always shown (it has the
  buttons) and a browser notification is sent only when the page is hidden, so the two never overlap.
- **Pause off:** each pop-up stays visible for at least `MIN_VISIBLE_MS` = 10 s of real time (or until dismissed or replaced) even if its target hour passes; it is
  then marked "(target hour now passed)" (or "(the forecast no longer reaches your alert level)") instead of being removed, and retired after 10 s (a timer also
  retires it when no further tick arrives). Station/profile change, jump, scrubbing or rewinding time still clear it at once (it no longer belongs there).
- **Replacement (unchanged intent):** one pop-up at a time; a newer alert replaces a STALE pop-up at once (cooldown rules still apply); an escalation (higher level or
  CPCB category) replaces a live pop-up at once. **Live mode is unchanged** (no pop-ups; e-mail only).
- Code: `frontend/app.js` markStale / tryRetire / expireAlert / maybeAlert / issue / clearAlert (replaced exactly this block). The older self-tests that exercise
  other behaviour (stepping, play consistency) run with pause-on-alert OFF unless `?pauseonalert=1`; their "stale alert" invariant now requires that an alert past its
  target hour is MARKED stale.
- Tests `backend/test_alert_popup.py` (24 checks, ALL PASSED): deterministic lifecycle with a controllable clock (`?selftest=popuplogic`: visible at 9.8 s, gone after
  10.1 s, marked when the target passes, newer alert replaces a stale one at age 2 s, escalation replaces a live one, pause stops the clock, both buttons, pinned for
  2 minutes, Continue/Dismiss, Play unpins) plus real playback at 1 h/s from 18 Apr (`?selftest=popup&mode=pause|nopause`): the first alert stops the clock for
  10 s with the pop-up and buttons present, Continue restarts and advances it, a second alert pauses again, Dismiss leaves it paused; with pause off 6 episodes in 90 s,
  every one that ended by itself had been visible 10 s, three were marked while their target hour had passed. Full regression re-run: stepping, 24 Apr escalation,
  playback consistency (1/6 h/s, delays, drags), sticky banners, live page, e-mail/outbox, scheduler, pollutants, jump: all pass; real e-mail log unchanged.

## DECISION (user, 17 Oct 2026): main pages show only +1, +6, +12, +24 h
- **Why:** in our tests +48 and +72 h have NO consistent skill over persistence (test MAE 12.68 vs 11.95 and 13.71 vs 13.13; validation 15.97 vs 15.44 and
  18.50 vs 18.53) and +36 h is MIXED (better than persistence in validation, MAE 14.31 vs 17.65; on the test period MAE 11.06 vs 11.65 but worse exact-category
  accuracy and within +-10 AQI points). Showing them as forecast cards would over-claim.
- **UI only. Unchanged:** alert rules (already <= 24 h: likely <= +24 h, possible <= +12 h), e-mail logic, the model, the stored predictions (`results/final`,
  `data/replay.db` keep all 7 horizons and the API still returns all 7), and ALL research results/report tables (1-72 h stay there).
- Replay + live: forecast strip = 4 cards; chart plots only the 1-24 h forecasts (replay axis -48 .. +26 h; live axis -96 .. max(26, ceil(age)+3), so the
  orange "now" line is always visible when the data is older than 24 h); main table in Details = 4 rows; "How earlier forecasts did" = 4 rows; "Upcoming"
  line uses only <= 24 h forecasts and the "Beyond 24 h ... tendency" sentence is gone; advice basis was already <= 24 h.
- Details has a separate small table "Experimental longer horizons (+36, +48, +72 h)": forecast (+category), likely range and persistence side by side, with the
  note "No consistent skill over persistence in our tests, shown for transparency only ... never used for the cards, the advice or any alert" (live: persistence =
  the last observed AQI). The "How to read the ranges and confidence" text now states the reason (36 h mixed, 48/72 h none).
- **Live, data too old:** when every 1-24 h horizon has already passed, the strip shows ONE message instead of cards: "No forecast for the coming hours: the newest
  data is N h old, so every forecast horizon (up to 24 h) has already passed." The gap is NOT filled with 36-72 h. The live warning counts only the four main
  horizons ("All 4 forecast horizons (up to 24 h) already lie in the past ..."; "1 of the 4 ... already lies ..."); the Upcoming line says the same.
- Tests: replay stepping now checks 4 table rows + 3 experimental rows + 4 cards at every step and that no chart point is beyond +24 h and the axis max is 26
  (80 steps, 0 violations); `?selftest=live` reports cards / message / rows / chart axis. Real data (82 h old): 0 cards + message, 4 + 3 rows, forecasts <= 24,
  axis max 86, now line 82.4. Test-only clock override `AQI_LIVE_NOW="YYYY-MM-DD HH:MM"` (in `live_api.now_ist`): data 5 h old -> 4 cards (+1 h greyed "passed
  4 h ago"), no message, axis max 26; data 30 h old -> message, axis max 33, now line 30. All other UI and backend suites re-run: 0 violations / ALL PASSED.
- Cosmetics fixed on the way: forecast cards share the row width on desktop (max 260 px), category pills never wrap ("Moderat/e"). The rule is global
  (`.catpill { white-space: nowrap }`), so it covers pills in every table and card. Measured (iframe check, details open) at 390 and 1100 px: replay 12 pills
  (7 in tables), live 8 pills (7 in tables) - none wrapped, none spills out of its table cell, all computed `white-space: nowrap`. If a pill still looks wrapped
  after a pull, hard-refresh (Ctrl+F5): the browser may be serving a cached `style.css`.

## "Skip to next pollution event (demo)" jumped BACKWARDS - fixed (2026-10-17)
- Bug (user run-through): from 19 Apr 09:00 it went to 18 Apr 03:00, then 17 Apr 08:00. Cause: it looked for the next event HOUR (any hour with AQI > 100)
  after the displayed hour; inside an episode that is the next hour, and "6 h before it" is in the past.
- New definition (server `backend/app.py find_onsets`, endpoint `GET /api/replay/events?period&station&alert_from`): an event is an ONSET - the AQI
  REACHING the user's alert level from below (AQI(t-1) < level <= AQI(t); the same "reaches" rule the alerts use, so a 100 -> 101 rise at level 101 counts and
  an already-alerting 101 -> 102 does not) OR the CPCB category rising to Moderate or worse (Moderate -> Poor, ...; Good <-> Satisfactory flicker is ignored).
  Both hours must be observed. The user's effective level is used (it can only be lowered from the profile default: lung 101, healthy 201).
  **User decision (17 Oct 2026): keep the "reaches" rule** (same as the alerts), NOT the literal "from <= level to above it" (which would miss 100 -> 101 at
  level 101 and count 101 -> 102 although the alert is already active). Do not change this without asking.
- Jump rule (`frontend/app.js pickJump/jumpToEvent`): search only FORWARD from the DISPLAYED hour; land on the first simulated hour at or after (onset - 6 h) and
  before the onset; an onset whose lead hour is not after the displayed hour is skipped (never backwards, never stays); if none is ahead the message
  "No more events in this period" is shown (`#jumpMsg`) and the display does not move. The page-load auto-jump uses the same rule.
- Test `backend/test_jump.py` (starts a fake-mode server, drives the real page in headless Chrome via `?selftest=jump`, verifies every press against an
  INDEPENDENT reference computed from `replay_obs`): Silk Board and Mysuru, validation and test period, profiles lung 101, lung 51, healthy 151,
  healthy 201 (51 and 151 are not category boundaries, so the level rule is tested on its own), 8 / 4 start hours each, chains of up to 5 presses:
  16 groups, 363 presses, 35 "no more events" cases, all correct: always later than the current hour, 6 h before a real onset (exactly 6 h when that hour
  exists), the first eligible onset, monotonic chains. Reported case: Silk Board from 19 Apr 09:00 -> 22 Apr 01:00 (onset 22 Apr 07:00).
- Developer switches added: `?station=mysuru`, `?period=test`. My first test attempt had two harness slips caught by the test itself (no `?station=` switch,
  and a "lung 151" profile - a level above the default is correctly capped to 101 by the page).
- **Process lesson:** a scripted slice-and-replace of app.js (from `jumpToEvent` to `bind()`) silently deleted two unrelated functions (`renderStrip`,
  `renderNowAdvice`) that sat in that range; the headless run showed "Could not start: renderStrip is not defined". Restored from git; the final diff
  against the last commit contains only the jump changes. After any scripted slice edit, diff against HEAD and run the page.

## Weather-app style UI redesign and pollutant fixes (2026-10-17; UI only, no model/alert/advice logic changed)
- Layout (replay `index.html` + live `live.html`; shared helpers in `frontend/ui.js`): sticky banner with gear -> settings drawer (profile, alert level,
  notifications, e-mail; live page: shared profile info, automatic-update status, e-mail pause note); big "now" card with CPCB colour band, category pill,
  main pollutant and a one-line personal advice; horizontally scrollable forecast strip, one card per real horizon (+36/+48/+72 greyed dashed "tendency",
  warning badge when it reaches the user's alert level, "(not notified)" outside the notification rules, "not available (data gap)" cards); tabs Forecast
  (chart) / Health advice (advice + disclaimer + sources) / Pollutants; collapsed "Details" (full table, "How earlier forecasts did", ranges explanation).
  Mobile checked at 390 px. Replay button label: "Skip to next pollution event (demo)".
- **Pollutants tab bug (user report):** bars showed the HOURLY concentration (PM2.5 92.9) next to a sub-index computed from the 24 h / 8 h AVERAGE (104.86 ->
  250; CPCB gives ~210 for 92.9). Now each pollutant shows "<24 h|8 h> average: X . sub-index N (category)" and a second line "now (hourly): Y"; bars use the CPCB
  0-500 scale with the CPCB colour bands. Data: `replay_obs` now stores `*_si` and `*_avg` (rerun `backend/make_replay_data.py` after any predictions
  change); `/api/replay/state` and `/api/live/state` return `pollutants` (value = hourly, avg, si, category, window) and live also `dominant_now`.
  `backend/test_pollutants.py` (9 checks): the shown average reproduces the shown sub-index through `aq_clean.subindex` for 400 random replay hours
  (2157 values, max difference 0.50 = rounding) and for every live station; the AQI equals the highest shown sub-index; hourly differs from the average in 93%
  of rows; the exact 24 Apr 02:00 Silk Board case; display names.
- **Display names:** PM2.5, PM10, NO2, SO2, O3, CO (with subscripts) everywhere - cards, tables, pop-ups, e-mails (`advice.pname`, `ui.js pn()`); never "PM25".
  Headless check of the rendered pages: 0 occurrences of "PM25".
- **Test output never renders on real pages:** the self-test `<pre>` is created only when a `?selftest=` switch is present and is hidden (`display:none`);
  a normal page load contains none. Developer switches: `?selftest=1|play|sticky`, `?tab=advice|pollutants`, `?settings=1`, `?details=1`.
- **Live banner on a phone:** wrapping is set by the attribute `data-wrap` (not `:has()`); measured at 390 px: white-space normal, not truncated, 3 lines,
  full sentence visible. Replay banner stays a single line with ellipsis.
- **Ruler label "500" wrapped to "5/0/0" at 390 px** (and on the live page a stray "0" overlapped the note text). Cause: an absolutely positioned label
  placed at `left:100%` has zero width available and wraps per character; `white-space: nowrap` alone was first measured on the replay page only. Fix:
  `nowrap` on all ruler labels and the "500" label is positioned with `right:0` (right-aligned inside the bar width, no transform). Measured at 390 px on
  BOTH pages (iframe check): every label one line (17 px), "500" right edge = bar right edge, no overlap with "400", ruler bottom above the note text;
  visual check of the live page scrolled to the ruler. Lesson: measure every page that uses a component, not just one.
- Preview helper files `frontend/_*.html` and `screenshots_preview/` are git-ignored (headless Chrome cannot go below ~500 px, so mobile screenshots are
  taken by framing the page in a 390 px iframe on the same server).
- Re-run after the redesign (all pass): stepping 3 h/step x 80 (16 pop-ups, 1 escalation), 24 Apr escalation case (163 -> 201 Poor -> 248 Poor), playback
  consistency at 1 and 6 h/s with delays and slider drags (0 violations, 17-22 stale responses dropped), sticky banners, e-mail/outbox, scheduler tests.

## Sticky banners and automatic updates (2026-10-16)
- **Sticky banner bug:** the REPLAY and LIVE banners scrolled away (measured: banner top = -1500 px after scrolling 1500 px). Cause: my earlier layout fix
  `html, body { overflow-x: hidden }` makes the body a scroll container, which silently disables `position: sticky`. Now `overflow-x: clip`.
  Verified headless on both pages at desktop (1200x700) and phone (400x800) widths: banner top = 0 after scrolling (`?selftest=sticky`).
- **Scheduler (`backend/scheduler.py`, APScheduler 3.11 inside the FastAPI process; OFF unless `AQI_SCHEDULER=1`)**: hourly at minute 10 (IST):
  `update_all.py --quick` (OpenAQ API tail of the last 7 days = still 96 calls, Open-Meteo forecast, rebuild database, `forecast_live.py`) then
  `notify_email.py --live` (only if `.env` e-mail is configured); daily at 03:40: full `update_all.py` (adds S3 archive + weather history).
  One update at a time (a second request is refused, never queued/overlapped); each job is a SUBPROCESS (a crash cannot kill the web server; timeout
  30 min); a failed update skips the e-mail step and leaves the database unchanged. `AQI_SCHEDULER_RUN_ON_START=1` also runs one update 15 s after
  start-up. Endpoints: `GET /api/scheduler/status`, `POST /api/scheduler/run-now?kind=hourly|daily`. Output: `data/update_log.txt`,
  `data/scheduler_status.json` (both git-ignored). The live page shows "Automatic updates: on/off, last update ..., next ...".
  Start it (PowerShell, aqi env, project root): `$env:AQI_SCHEDULER="1"; python -m uvicorn backend.app:app --port 8000`.
  The machine must stay on and the server running; while the OpenAQ feed is dead the e-mail check only sends the daily "feed stopped" notice.
- `backend/test_scheduler.py` (13 checks, harmless stub commands, no network/e-mail): jobs at :10 and 03:40, overlap refused, success/failure
  recorded, e-mail step skipped after a failure, quick vs full commands, disabled by default (409). SQLite: 30 s timeouts on readers and WAL mode in
  `build_dataset.py` so the web server is not blocked while the update rewrites tables.
- Real check: `update_all.py --quick` ran end to end in 4 min 30 s (16 Oct 22:24); live forecasts now use the trained models in `models/live/`
  (method "model", trained through 13 Oct 22:00). OpenAQ was still stale (newest reading 13 Oct 23:30). Ramanagara has no forecast (no valid AQI in 7 days).

## E-mail alerts (built 2026-10-16; `backend/notify_email.py`; needs `.env` lines the user adds)
- `.env`: `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD` (Google app password: needs 2-Step Verification; https://myaccount.google.com/apppasswords),
  `ALERT_EMAIL_TO`. Sent via smtp.gmail.com:465 (SSL). The password is never printed or logged; `data/email_log.jsonl` keeps only time/to/subject.
- Decisions (user, 16 Oct): no LIVE alert e-mails when the newest observation is > 12 h old; instead ONE "data feed stopped" notice per day when
  every station is > 24 h old. Replay mode may send alert e-mails for the viva demo, subject starts with "[REPLAY DEMO]" and the body says the alert
  is simulated. Only groups, station, alert level and e-mail are stored, in `data/profile.json` (git-ignored; alert level may be lowered, never raised).
  Scheduling: manual commands first; after the test e-mail works, APScheduler inside the backend.
- Rules as on the page: Likely <= +24 h, Possible <= +12 h, nothing >= 36 h, 12 h cooldown per station (state in `data/email_state.json`).
- Commands (project root, aqi env): `python backend\notify_email.py --test` (test e-mail), `--live [--dry-run]`, `--replay-demo [--dry-run]
  [--station S --time "YYYY-MM-DD HH:MM:SS"]`. `--dry-run` prints the e-mail instead of sending (works without `.env`).
- API: `GET/POST /api/profile`, `POST /api/email/replay-alert` (server recomputes the alert from the saved profile; max 1 per 60 s and 10 per hour).
  Replay page: e-mail field, "Save profile for e-mail alerts", checkbox "Also e-mail replay alerts".
- Tested without credentials: dry-run composition for test, replay and live (live at 58 h data age correctly sends nothing but composes the daily
  feed-stopped notice); profile validation (cap at default, bad group dropped, bad e-mail -> 400); replay e-mail without `.env` -> 503; playback
  self-test unchanged (15 pop-ups at 3 h/step, 0 violations). NOT yet tested: real sending (waiting for `.env`).
- Live models: `backend/train_live.py` (smoke-tested on a subset: train -> joblib -> load -> predict works); full training run by the user in their
  own terminal, ~50 min for 7 horizons, writes `models/live/h<h>.joblib` (git-ignored); then run `python backend\forecast_live.py`.

## Website fixes after first user feedback (2026-10-15)
- Category is computed from the DISPLAYED rounded integer AQI (100.4 -> 100 -> Satisfactory; CPCB 51-100). Server (`advice.rint`) and page use
  the same round-half-up. Note: the research metrics (`aq_model.metrics`) take categories from the unrounded float predictions; rounding first
  would be more faithful to CPCB and is a small possible change (it would alter category accuracy slightly; not applied to the official run).
- API always returns all 7 horizons; missing ones are flagged `available: false` and shown as "not available (data gap)".
- Alerts: one small corner pop-up at a time; shows "Issued <sim time> - for <target time> (+h)"; removed when the target hour passes, the
  station or profile changes, the condition clears, or time is rewound; 12 h simulated cooldown per station (escalation possible -> likely still
  alerts); "Likely" pop-ups only up to +24 h, "Possible" only up to +12 h, nothing for +36 h and beyond (table only).
- Advice card wraps; "Upcoming (next 24 h)" line added; advice is based on the higher of now and the next-24 h forecasts (not 36-72 h).
- Chart: x axis in hours from "now"; observed line ends exactly at 0; dots at exactly +1/+6/+12/+24/+36/+48/+72 with tick marks there.
- Self test (headless Chrome, `?selftest=1&speed=S&steps=N`, Silk Board, validation, demo profile): 1 h/step x 150 steps: 10 pop-ups, max 1 at
  a time, 0 violations; 3 h/step x 80 steps: 21 pop-ups, max 1 at a time, 0 violations (7 table rows every step, no stale alert, no pop-up
  for >= 36 h or "possible" > 12 h, categories match the rounded integers).

## Final-check fixes (17 Oct 2026): UPDATE label, Test notification, "Server not running" bar
- **UPDATE label.** User saw "UPDATE, higher category ... AQI 132 (Moderate)" at Mysuru 20 Apr 13:00 and asked whether the previous alert was also Moderate.
  The exact sequence was not reproducible with the demo profiles (healthy 151 gives "Possible ... 132 Moderate" then "UPDATE, higher alert level ... 159" at 16:00),
  but the label rule had a real flaw: "category" was compared with the previous alert's FORECAST category, so a Possible alert (forecast Satisfactory, "could reach
  Moderate") followed by a Likely Moderate alert read "higher category" although it already warned about Moderate. Fix (`warnedRank` in app.js): a Possible alert
  counts as having warned about the category of the upper end of its range (`category_high`); "higher category" only if the new alert is above what the previous one
  warned about, otherwise a possible -> likely change says "higher alert level"; same category and level = no UPDATE. Possible alert text and e-mail now also show
  "could reach 132 (Moderate)". The stepping self-test audits every UPDATE label against the previous alert; `test_alert_popup.py` has 7 synthetic label cases (M1-M7).
  Real replays with lung 51 still say "higher category" for 71 Satisfactory -> 107 Moderate, which is correct (previous alert warned about Satisfactory only).
- **Test notification** button (Settings drawer, replay page): granted -> sends one test notification; blocked/unsupported/refused -> explains in the status line and shows an
  in-page toast. Never counts as an alert. **"Server not running"** red bar on both pages (shown on failed fetch or page opened as file://; shows the start command
  `python -m uvicorn backend.app:app --port 8000`; hides itself and reloads when the server is back; an HTTP error from a running server does not trigger it).
  Test: `backend/test_server_bar.py` (port 8033; 15 checks).

## User accounts and per-user e-mail alerts (built 20 Oct 2026)
- Files: `backend/users.py` (SQLite `data/users.db`, git-ignored; test override `AQI_USERS_DB`), `backend/auth_api.py` (router), pages
  `frontend/signup.html`, `login.html`, `profile.html`, `forgot.html`, `reset.html` + `frontend/account.js`; "Log in / Sign up" or "Profile: <name>" link on
  the replay and live pages. **Guest mode unchanged** (browser-only profile; replay demo works without login).
- Security: Argon2id hashes (argon2-cffi, already in the aqi env), min 8 characters; session = random 256-bit token in an HttpOnly, SameSite=Lax cookie
  `aqi_session` (Secure only over https: the site runs on http://127.0.0.1), 14 days; the DB stores only HMAC-SHA256(secret, token). Secret `AQI_SECRET_KEY` from env
  or `.env`; if missing it is generated once and appended to `.env`. Changing requests from another Origin -> 403. 5 wrong passwords per e-mail in 15 min -> 429.
  Unknown e-mail and wrong password give the same message; "forgot password" answers the same for any address.
- No endpoint takes a user id: `/api/me` (GET/PUT), `/api/me/delete` (needs the password), `/api/me/send-verification` all use the session's user.
  Others: `/api/auth/signup|login|logout|forgot|reset`, `GET /api/auth/verify?token=`, `/api/account/options`.
- E-mail verification + password reset (optional extras, done): one-time links (verify 24 h, reset 1 h), stored hashed; a reset also confirms the address and logs out
  all sessions. **Alert e-mails (live and replay) go only to CONFIRMED addresses** (so nobody can make the system mail someone else's address).
- Profile: name, age (0-120, optional), home station, conditions (lung, heart, pregnant, outdoor_worker, athlete), alert level (NULL = default; a stored value only
  below the default; re-capped when the profile changes), live e-mail alerts on/off, replay-demo e-mails on/off. Age < 14 -> Child ([4]); age >= 60 -> Older
  adult (**design choice**, written in docs/health_advisory_reference.md section 2 and on the profile page). E-mail address cannot be changed (it is the login).
- Delete account removes the user row, sessions, link tokens (ON DELETE CASCADE), their cooldown state, their outbox items and their lines in `data/email_log.jsonl`.
- Live e-mails (`notify_email.run_live`, run hourly by the scheduler): loop over accounts with alerts on + confirmed address; each user's own station, groups and
  level; same rules (Likely <= 24 h, Possible <= 12 h, 12 h cooldown per user+station key `user<id>:<station>`, escalation bypass, no alert when the user's station
  data is > 12 h old). The daily "feed stopped" notice still goes only to ALERT_EMAIL_TO. **Change:** the guest profile (`data/profile.json`) no longer gets live e-mails.
- Replay e-mails: logged in -> account profile + own address (403 if replay e-mails off or address unconfirmed); guest -> as before. Outbox supersedes only e-mails to the
  same address+station; `/api/email/outbox` lists only the caller's own (user or guest) e-mails.
- Tests: `backend/test_accounts.py` (87 checks, in-process TestClient, no port, temp DB, fake e-mail + SMTP class that raises; checks the real e-mail log and users.db are
  untouched). Re-run 20 Oct: test_accounts, test_email_rate_limit, test_scheduler, test_pollutants (needs `PYTHONIOENCODING=utf-8` when piped), test_server_bar,
  test_alert_popup, test_jump: ALL PASSED; replay stepping 3 h x80 and 1 h x60 and playback 6 h/s with delays+drags: 0 violations (test server port 8042).
- Screenshots: `screenshots_preview/acct_*` (sign-up, login, profile; desktop + 390 px; replay settings when logged in), made with a temp server on port 8041.
- **Login first (user request, 20 Oct 2026):** `/`, `/index.html` and `/live.html` are served by `app.gated_page`: no session and no guest choice -> 303 to
  `/login.html?next=/` (or `next=/live.html`), `Cache-Control: no-store`. The login page has "Create an account" and the link **"Try the demo without an account
  (guest)"** = `/?guest=1` (or `/live.html?guest=1`), which sets a browser-session cookie `aqi_guest=1`; logout clears it. `?selftest=` requests are let through
  (the headless UI tests run as guests). Login and sign-up pages send logged-in users straight to `next` (only `/` or `/live.html` allowed).
- Flow: sign-up -> `profile.html?welcome=1` (green "add your details" note + blue "please confirm your e-mail" reminder) -> **Save profile** -> "Profile saved.
  Opening the replay demo..." -> replay page after 1 s (every save does this). Header line on replay, live and profile pages (`ui.js renderAcctNav`):
  "Signed in as <name> · Profile · Log out" or "Guest (no account) · Log in / Create account".
- Tests: `test_accounts.py` now 97 checks (F1-F10 gate). Browser check with a temp server on port 8041 (scratch script): not logged in -> login page for `/` and
  `/live.html`; guest link -> replay; Save -> message -> `/` about 1 s later; logged in -> `/login.html` goes to the replay page. Screenshots `screenshots_preview/flow*`.
- **Bug (user report, 20 Oct): profile page "Could not load: Cannot set properties of null (setting 'textContent')", empty form, Log out dead; replay header
  "Profile: Kusuma" without Log out.** The code itself was consistent (every id `account.js` uses exists). Cause: STALE BROWSER CACHE. Static files had no
  Cache-Control, so the browser reused an old `account.js` (which still set the removed `#hello` line) with the new `profile.html`, and an old `ui.js`/`app.js`
  (that "Profile: <name>" text exists only in the older `showAccountLink`). Fixes: middleware `no_stale_files` sends `Cache-Control: no-cache` for all non-API files
  (browser re-checks, 304 if unchanged); all pages link `?v=20261020b` versions of scripts/styles (bump it when changing scripts); account code uses the guarded
  lookup `el(id)` (ui.js: missing element -> console.error + detached placeholder, never a crash; `$` is unchanged because old self-tests rely on it returning null);
  Log out always ends on the login page; empty favicon (`<link rel="icon" href="data:,">`) so the browser console has no 404. **Lesson: after changing a page and
  its script, test in a browser profile that already holds the OLD files, or version the links.**
- Test `backend/test_pages_logged_in.py` (19 checks; Chrome DevTools protocol via websocket-client; server port 8034, DevTools 9334): no console errors /
  exceptions / failed requests on profile, replay and live while logged in; saved name/age/station/conditions/alert level/e-mail switches in the form; header
  name/Profile/Log out on every page; Log out (header on all 3 pages + profile button) -> login page and session ended; a simulated missing element is reported but
  the form still fills; no-cache headers and versioned links.

## Personalised advice, no duplicate e-mails, page switch (user request 20 Oct 2026)
- **Advice from parts** (`advice.personal_advice`, sources in `docs/health_advisory_reference.md` section 7 with page numbers): headline (category + CPCB impact
  [1][2]); what to do [3]; ONE LINE PER HEALTH GROUP the user has (CPCB impact wording naming the group + NCDC vulnerable-population action by category from the HAP
  2021 posters [4]; WHO risk-group / timing statements [5]); trend (rising / falling / changing / steady, from +1/+6/+12/+24 h) and best time to go out (cleanest
  DAYTIME 07-20 h forecast hour; night hours excluded) labelled "(our forecast)"; main pollutant in plain words (WHO [6][7]); rotating tip; doctor line at alert level;
  WHO mask caution from Very Poor. **New sources:** [6] WHO "How air pollution is destroying our health" (spotlight, n.d., accessed 20 Oct 2026), [7] WHO "Ambient
  (outdoor) air pollution" fact sheet (24 Oct 2024). [4] PDF moved to https://ncdc.mohfw.gov.in/uploads/pdf/air7.pdf (old link 404). The NCDC advisory on HAP
  pp. 44-45 was written for severe-plus AQI, so its items are used only from Poor / Very Poor upwards. The ASHA handbook [3] PDF is a scanned image (not re-read).
- Pop-up = forecast line + at most 4 BRIEF lines (group action, trend + best time, "Mainly <pollutant>: ...", tip); full wording in the Health advice tab and
  the e-mail. Pop-up layout: only the lines scroll; Continue/Dismiss always visible (was hidden on phones). Tip number `seq`: localStorage `aqiTipSeq`, +1 per
  alert, sent with `/api/replay/state?seq=` and in the e-mail request, so the pop-up and its e-mail show the same tip; live e-mails use the user's sent count.
  `/api/advice` (live page) takes optional forecasts / now_aqi / dominant / seq and returns `personal`.
- **No duplicate e-mails:** table `sent_alerts` in `data/users.db` (user_key `u<id>` or `guest:<address>`, mode, station, issued, target, level; PRIMARY KEY on all)
  claimed atomically (INSERT OR IGNORE) before queueing; released only if not queued or the send failed. Replay: issued = simulated hour; live: issued =
  newest observation time. Restart/rewind of the replay can never repeat an e-mail; possible -> likely (different level) is a new alert. Deleted with the account.
- UI: segmented switch "▶ Replay demo | ● Live data" under the title on both pages (current page highlighted, `aria-current`; full width on phones); Profile and Log out
  are small buttons (`.btn-sm`). Script/style links now `?v=20261020c`.
- Tests: `backend/test_advice.py` (25 checks: citations on 45k generated lines, 8 profiles give 8 different first lines, consecutive alerts differ, no N95 below Very
  Poor, no inhaler, daytime best time, trend wording, replay + live endpoints); `test_accounts.py` 107 (N1-N9 duplicates: repeat, restart, rewind, guest, failed send);
  `backend/test_popup_advice.py` (13 checks, CDP, port 8035/9335: two accounts, lung vs child pop-ups differ, consecutive alerts differ, <= 5 lines, no JS errors,
  switch on both pages, phone width; writes `screenshots_preview/popup_*` and `switch_*`).

## Reliable "best time" and tips (user request 20 Oct 2026, replaces the forecast-based best time above)
- **Best time is NOT taken from the 4 AQI forecast points** (CPCB AQI is a 24 h average). `backend/diurnal.py`: per station, median hourly PM2.5 and PM10 per
  hour of day over the 28 days BEFORE the current / simulated hour (rows in (t-28 d, t], measured hours only: `real_pm = 1`); an hour counts if both have
  values on >= 20 of 28 days; hour score = mean of (hour median / window median) of the two; cleanest 3-hour block within 6 am-9 pm vs worst 3-hour block
  of the day; shown only if >= 20 % lower: "Usually cleanest at this station: 1-4 pm; usually worst: 7-10 pm (typical pattern from the last 4 weeks, not a
  forecast) [5]", else "No clearly better time at this station" (or "... not enough measurements"). Very Poor / Severe: "Limit outdoor activity at all
  times [3]". "ⓘ How is this calculated?" note (collapsed) under the line in the pop-up and advice tab, and in the e-mail. Hour labels are hour-start.
- Replay data: new table `replay_pm` in `data/replay.db` (from 16 Mar 2026, so the first replay hour has 28 days of history; `make_replay_data.py` writes it,
  rerun done 20 Oct). Live: `data/aqi.db hourly` up to the newest observation. Results vary by station (e.g. Silk Board 24 Apr: cleanest 1-4 pm, worst 7-10 pm,
  27 % lower; Mysuru usually 6-9 am; Chikkaballapur often "not enough data" because of gaps).
- **Tips:** only the exact list in `docs/health_advisory_reference.md` section 7 ("Tips"), each with [n] and a lowest category; N95/N99 only from Very Poor and
  never for a child (children at Very Poor get "There are no commercial respirators designed for children [5]"); profile-specific tips first (outdoor worker
  water breaks [3], exerciser timing [5], lung/heart respirator caution [5]). Tip index = **alert number = hours since 2026-01-01 of the issue time**
  (`advice.alert_number`): the same alert always shows the same tip (pop-up, e-mail, after reload/restart); alerts issued at different hours rotate. (Two alerts
  whose issue hours differ by a multiple of the pool size get the same tip; accepted.) The old browser counter `aqiTipSeq` is gone.
- Pop-up: forecast headline + 1-2 profile lines + trend + best time + 1 tip (main pollutant only in the full version). Links `?v=20261020d`.
- Tests: `test_advice.py` rewritten (40 checks: no-leakage proof on the real replay DB with every later hour set to 9999, 19 vs 20 of 28 days, gap-filled hours
  ignored, no-clear / not-enough / Very Poor / Severe cases, every tip cited, in the document and allowed for its category and profile, same alert -> same tip
  in state, e-mail and repeated calls); `test_popup_advice.py` 14 checks (adds: same hour again -> same tip).

## UI polish: one formal design system (user request 21 Oct 2026; visual only, no model/alert/advice/e-mail/account logic changed)
- `frontend/style.css` rewritten as the single design system: tokens on `:root` (navy #0b3c5d / teal #0f6e78 primary, neutral greys, white cards, dark-mode set),
  Inter (bundled locally since 21 Oct, see below; system-font fallback), tabular figures for numbers, 8 px spacing grid, buttons primary (default `button`) /
  secondary (`.secondary`) / subtle (`.subtle`) / `.btn-sm`, labelled form fields with `.field-hint`, visible `:focus-visible` outline, skip link.
  CPCB category colours only for AQI values, pills and their coloured edges; pill text colours chosen for WCAG AA (Satisfactory/Moderate/Poor pills now dark text;
  the old white-on-light-green Satisfactory pill failed AA). All text/background pairs checked >= 4.5:1.
- Every page: top bar (logo + "Karnataka Air Quality & Health Alerts" left, "Replay demo | Live data" switch centre, user menu `#acctNav` right); status banner
  sticky directly under it (top bar sticky from 768 px, `--head-h` 64 px; on phones the top bar scrolls away and the banner sticks at 0; the `?selftest=sticky`
  check now compares with `stickyTarget()`); footer (disclaimer summary, "Sources and full disclaimer" = `#sources` with `#disclaimer`/`#refs`, "Student research
  prototype", data OpenAQ + Open-Meteo; account pages fill it via `ui.js initFooter` from `/api/meta`).
- Replay/live: page heading, controls card, dashboard grid (>= 1024 px: left = current AQI card with a CPCB 0-500 scale bar `#nowScale` (`ui.js renderScale`) +
  4 equal forecast cards; right = "Personal advice" card holding `#nowAdvice`); tabs + chart full width; phones single column, forecast cards 2 x 2.
  Alert pop-up: card with a 6 px left edge in the forecast category colour (class `cc-<Category>` added in `issue()`), title, summary, bullets, buttons right-aligned.
  Chart.js uses the site font. Login / sign-up / forgot / reset: centred card with logo, project name and one-line description; consent in small print.
- New endpoint `GET /api/auth/session` (always 200, `{"user": ... | null}`) used by `getAccount()` and the profile page, so a logged-out page no longer logs a 401
  in the console (`/api/me` unchanged). Script/style links `?v=20261021a`.
- Checked: 21 views (login, replay with alert, live, profile; 1366 / 768 / 390 px, viewport + full page) with 0 console errors and no horizontal scroll;
  screenshots `screenshots_preview/before/` and `screenshots_preview/after/` (script in the session scratchpad `shots_ui.py`, ports 8036/9336).
- **Inter bundled locally (21 Oct 2026):** `frontend/fonts/inter-latin-wght.woff2` + `inter-latin-ext-wght.woff2` (Google Fonts' variable Inter v20, weights
  400-700, the "latin" and "latin-ext" subsets; the site's text needs nothing else, other characters such as the subscript in NO2 fall back to the system font
  exactly as before) + `OFL.txt` (SIL Open Font License 1.1: bundling allowed). `@font-face` rules at the top of `style.css` (same unicode ranges as Google);
  no page refers to Google Fonts any more; served as `font/woff2` (`mimetypes.add_type` in app.py). Links `?v=20261021b`.
  Test `backend/test_fonts.py` (10 checks, port 8037/9337): with every https request blocked, login, sign-up, replay, live and profile load only local files,
  render in Inter, 0 console errors. Screenshots with the local font are pixel-identical to the Google-hosted version (login, profile, replay; live differs only
  in its time-dependent text).

## Design review fixes (21 Oct 2026)
- Trend icon follows the direction: the trend part carries `dir` (up / down / changing / steady; presentation only) -> list markers ↗ ↘ ↕ →; the best-time
  line ("Usually cleanest ...", "No clearly better time", "Limit outdoor activity") has a clock icon (CSS mask), no arrow.
- Alert pop-up while the replay is paused (pinned) = modal dialog: `#toasts.modal` fills the screen as a dimmed backdrop, the card is centred (desktop) or a
  full-width bottom sheet (<= 767 px; note: `#toasts` is a COLUMN flexbox, so vertical placement is `justify-content`). role="alertdialog", aria-modal,
  focus moves to "Continue replay" and is kept inside; Esc = Dismiss (replay stays paused); focus returns afterwards (`syncAlertModal()` in app.js, called
  from issue(), clearAlert() and play()). Without pause-on-alert, or after Play, it stays the small corner card.
- Phone banner: `#simTimeShort` ("24 Apr, 02:00 IST", `ui.js bannerShort`) replaces the long time below 561 px and the banner may wrap; `#simTime` keeps the
  long form (the consistency self-test reads it).
- Signed-out pages (login, sign-up, forgot, reset): no mode switch (`.topbar-simple`). Profile page: no in-page Log out button (`#logout` removed; the top bar's
  `#navLogout` is the only one) and no duplicate project-name block. Links `?v=20261021c`.
- Tests: `test_popup_advice.py` now 25 checks (I1-I2 icons, M1-M5 modal / bottom sheet / Esc / focus / backdrop over the advice card, S1 full short banner time,
  L1 no switch on login); `test_pages_logged_in.py` P8a (no duplicate Log out / heading) and P8/H3 use the top-bar Log out.

## Branding and source check (21 Oct 2026)
- No logo/icon anywhere (top bar, account cards; favicon stays the empty `data:,` so the browser requests none). Top bar: "Integrated Air Quality & Health
  Risk Prediction Framework" + subtitle "for Sustainable Urban Environments · Karnataka" (>= 1280 px); "AQ & Health Risk Framework" below 1280 px (subtitle
  hidden below 1024 px; on phones .875rem, ellipsis on very narrow screens). Login / sign-up / password cards show the full title + subtitle. Tab titles
  "<page> · AQ & Health Risk Framework". Links `?v=20261021d`.
- **Sources verified on 21 Oct 2026 from the raw page HTML** (exact sentences + URLs in docs/health_advisory_reference.md section 7): [6] WHO spotlight (no date
  on the page): "Smaller, more health-damaging particles with a diameter of 2.5 microns or less (≤ PM2.5 – 60 of them make up the width of a human hair) can
  penetrate the lung barrier and enter the blood system, affecting all major organs of the body." [7] WHO fact sheet (published 24 Oct 2024): NO2 and CO
  sentences. The six pollutant lines were reworded to follow this wording (PM2.5: "60 of them", not "about 60"; "penetrate the lung barrier and enter the blood
  system"; PM10: "causing irritation and inflammation").
- [4] level check: "Avoid outdoor physical activities" for the vulnerable population is the **Poor** level (HAP 2021 poster p. 38 and Appendix 1 p. 57; the poster on
  p. 42 says "Avoid outdoor physical exertion" for Poor); Very Poor = "Remain indoors and keep activity levels low". Kept at Poor.
- Profile (group) lines contain only the advice; the CPCB impact sentence (which names lung/heart disease, children, older adults) appears once, in the headline
  line (e-mail and Health advice tab). `_NAMED` removed from advice.py.
- Tests: test_advice Q1-Q4 (no repetition incl. a real e-mail body, PM2.5 wording, [4] levels); test_fonts B1-B2 (no logo, tab titles, full title on desktop and
  on the login card); test_popup_advice L2 (phone: short title on one line).

## WhatsApp alert channel via Twilio (built 24 Oct 2026; committed 2297e4b, not pushed)
- `backend/notify_twilio.py`: `send_whatsapp(to, text, on_result=...)` with the official `twilio` package (9.12.0, in requirements.txt). Credentials only
  from env/.env (`TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM=whatsapp:+17372508034`); never printed or logged. Same fake guard as e-mail:
  `AQI_EMAIL_FAKE=1` (or `AQI_WHATSAPP_FAKE=1`) -> in-memory `FakeClient`, no Twilio client is ever created. Twilio usually ACCEPTS a message first and reports
  63015 (not joined) / 63016 (outside 24 h) a few seconds later, so each send is followed by a delivery-status check (`AQI_WA_CHECK_S`, default 8 s) whose
  result is stored per user (`users.wa_last`) and shown on the profile ("Last WhatsApp delivery failed: <reason> (Twilio error <code>)").
  Rate limit 1 per 60 s, 10 per hour, persisted in `data/whatsapp_rate.json`, separate from the e-mail limit. Log `data/whatsapp_log.jsonl`: time, masked number,
  status, sid, error code; no token, no text. Both files git-ignored. Messages < 600 characters (`MAX_LEN = 599`), plain text, no links.
- `users.db` new columns (added automatically to an existing db): `whatsapp` (E.164), `whatsapp_alerts` (live), `replay_whatsapp`, `wa_last`. Turning WhatsApp alerts
  on needs a number; e-mail confirmation is not needed for WhatsApp (the sandbox join is the opt-in).
- Live alerts (`run_live`): accounts with e-mail (confirmed) and/or WhatsApp; ONE cooldown per user+station shared by both channels, same stale-data rule, a
  separate "already sent" record per channel (mode `live` / `live-whatsapp`, `replay` / `replay-whatsapp`); a failure (or rate limit) on one channel never stops
  the other and releases only its own claim. Replay alerts: the same outbox; each item has a `channel`; the worker reserves the slot of the item's own channel
  and wakes as soon as something new is queued (an e-mail is not delayed behind a rate-limited WhatsApp). `/api/email/replay-alert` returns the e-mail result plus
  `whatsapp`. `POST /api/me/test-whatsapp` (rate-limited) = "Send test WhatsApp" on the profile page.
- Tests: `backend/test_twilio.py` (38 checks; in-process app + profile page on port 8039/9339; real `twilio.rest.Client` and SMTP replaced by raising classes):
  phone validation, message length, channel selection, rate limit, shared cooldown, escalation, de-duplication, failure isolation, 63015/63016 on the profile, test
  button, replay queue, delete account, token in no log/output/response. NOT tested: a real Twilio delivery (needs the user's joined phone).

## Twilio trial findings and Content Template support (24 Oct 2026; committed 2297e4b)
- **What this trial allows (checked with the account's own API, read-only):** account type Trial; Content API v1 (list / create templates, approvals) ->
  HTTP 401, error 20003 "This feature is not available on a Trial account". The only outbound messages in the account were Twilio's own "Standard
  auto-reply" (sent after the phone messaged the sender); our free-form test at 12:30 IST was rejected with 21654 although it was INSIDE the 24 h window.
  Twilio docs (docs/usage/trials/try-out-whatsapp): during the trial only `to`, `from`, `ContentSid` (one of the Twilio-provided templates on the Console's
  Try out WhatsApp page) and `statusCallback`; "You won't be able to write your own message"; up to 5 verified recipients. Real test 1 of max 3 (24 Oct):
  ContentSid HXb5b62575e6e4ff6129ad7c8efe1f983e from Twilio's public quickstart -> 21655 "ContentSid is Invalid" (rejected, nothing delivered).
  => On this trial NO alert content can be sent by WhatsApp; only a fixed Twilio demo template whose id is shown in the Console (not readable by API).
- Code: `TWILIO_WA_CONTENT_SID` (HX...) + `TWILIO_WA_CONTENT_LAYOUT` (`aqi5` = our 5-variable AQI template: station, AQI + category, time, Likely/Possible,
  advice; `none` = fixed template, no variables) -> `send_whatsapp` sends ContentSid (+ ContentVariables, single-line, <= 1024 chars each); without the SID it
  sends Body text as before. `notify_twilio.alert_fields()` builds the variables; `TEMPLATE_BODY` = "Air quality alert ({{4}}) for {{1}}: forecast {{2}} for
  the {{3}}. {{5}} Not medical advice; in an emergency call 112." `backend/create_wa_template.py` (dry run by default; `--create` only on an UPGRADED account)
  creates it and requests WhatsApp UTILITY approval. Readable errors: profile shows "<code>: <reason>" once (21654 only approved templates, 21655 invalid
  template id, 21656, 63027, 63028, 20003 trial feature); unknown codes use Twilio's own message. The stored 21654 reason in data/users.db was rewritten.
- Tests: `test_twilio.py` now 44 checks (P1-P6 template / Body fallback / variables / readable reasons; U1 code shown once).

## SMS test (25 Oct 2026): channel NOT built
- One real free-text test SMS via Twilio was refused with error 572006 (trial account). Per the user's rule ("if rejected, stop"), no SMS channel was built.

## Weekly card "This week's air and your health" (built 25 Oct 2026)
- `backend/weekly.py` (tracking) + `backend/weekly_advice_rules.json` (every health/action sentence, with source ids, groups, levels; clean C1-C2,
  short_term S1-S12, long_term L1-L4, actions A1-A14) + `GET /api/weekly?station&mode=replay|live&t&groups` + `ui.js renderWeekly/loadWeekly`;
  card on index.html (replay clock), live.html and profile.html (home station, live data).
- Rules: the 7 complete days before the clock (a day counts once its 23:00 hour is <= clock; no data after the clock is read - poison test K3).
  Daily values need >= 16 of 24 hours (CPCB rule); O3/CO = max 8 h mean (>= 6 h); daily AQI via `aq_clean.aqi_from_averages`. >= 5 of 7 valid days, else
  "Not enough data for a weekly summary" and no health text. Trend = mean AQI of the last 3 days vs the previous 4; "steady" unless the change exceeds max(10 AQI points, 10%).
  Persistent = >= 4 of 7 days AQI >= 101 -> only then the "If this continues" (long-term) section. Exceedance counts vs India NAAQS 2009 [9]
  (PM2.5 60, PM10 100, NO2 80, SO2 80 ug/m3 24 h; O3 100 ug/m3 8 h; CO 2 mg/m3 8 h) and WHO AQG 2021 [8] (15, 45, 25, 40; O3 100 8 h; CO 4 mg/m3 24 h).
  Notes shown: India limits may be exceeded on 2% of days but not two consecutive days [9]; WHO 24 h levels are 99th percentiles (3-4 days/year) [8].
- Sources verified with exact quotes in `docs/health_advisory_reference.md` section 8 (NAAQS Gazette 2009 via cpcb.gov.in; WHO AQG 2021 via IRIS REST API;
  WHO fact sheet; NCDC 2021 pp. vii, 6, 25, 41). Disclaimer "General information from public health guidance, not medical advice." on the card.
- Phones (< 480 px): bar labels shortened to Mod./Sat./V.Poor (full names in the aria-label). Asset version `?v=20261025b`.
- Tests `backend/test_weekly.py` (40 checks incl. headless page checks on port 8040, screenshots in `screenshots_preview/weekly/`): all pass.
- NOT built: the optional Sunday weekly e-mail. EPA/AirNow not used.
- **Review fixes (25 Oct 2026):** (1) "no commercial respirators designed for children" re-verified in the WHO Q&A [5] page HTML, question "Can respirators
  protect from air pollution in the occupational setting?", exact: "There are no commercial respirators designed for children (based on information available as of
  February 2019)." Kept, now WITH that date qualifier everywhere (A12, advice.py tip/WHO_MASK/child line). The tip "...cautious with respirators and ask their
  doctor" was NOT in WHO's text -> "WHO advises special caution with respirators for people with heart or lung disease" (WHO: "a special caution is necessary for
  people with respiratory and cardiovascular disease"). (2) Pregnancy outcomes (low birth weight / growth restriction) only in L4 (long-term, persistent, pregnant);
  S6 (short-term) only says pregnant women are more vulnerable. Tests PG1-PG4. (3) `docs/weekly_advice_review.md` generated by `backend/export_weekly_review.py`
  from the JSON (test X1 fails if it is out of date; re-run the script after any rule change). test_weekly.py now 45 checks.
- **Fixes 26 Oct 2026 (screen-recording review):** (1) LIVE / profile with newest data > 24 h old (`weekly.STALE_AFTER_H`; age = now - end of the newest PM
  hour, `live_api.now_ist`, honours `AQI_LIVE_NOW`): API `data.stale`; card title "Last available week (7-13 Oct)", red line "Data feed stopped: newest data is
  N h old; this is not the current week.", headings "That week" / "During that week, air like this may affect you" / "If air like that week's continues" ("of those
  7 days"), chip "That week: ..."; rule texts past-tensed by `weekly.past_tense` ("this week" -> "that week"; C1, S10-S12). Replay unchanged ("This week", chip
  "Last 7 days: ..."). (2) Footnote under the limits table: each [n] once (`ui.js wkNote`). (3) Hedged: S11 / advice PM10 "which can cause irritation and
  inflammation"; S12 / advice O3 "WHO calls (it) a major factor in causing asthma ..."; test H1 forbids unhedged cause/causes/causing. (4) Forecast trend lines
  (pop-up, advice card, e-mail) now "Next 24 h: rising/falling/steady ... (our forecast)". (5) Profile: last WhatsApp failure 21654 -> grey note "WhatsApp needs a
  paid Twilio account to send our alert text" (test_twilio U4). test_weekly.py 56 checks (ST1-ST6, U6-U8, H1-H2); screenshot `weekly_live_stale_desktop.png`.
- **Wording review 26 Oct 2026:** S1 (headache, giddiness, ...) for vulnerable groups from a Moderate worst day, for healthy adults only from Poor (rule field
  `min_category_healthy`). New C3 (clean week reaching Satisfactory, vulnerable groups only): "At Satisfactory levels, air may cause minor breathing discomfort to
  sensitive people." [2][3] - Arthapedia [2] verified; the old CPCB report URL [1] returned an HTML page, so [1] is not cited for it. **[1] URL (26 Oct 2026):** official copy now https://airquality.cpcb.gov.in/ccr_docs/FINAL-REPORT_AQI_.pdf (same report, cover CUPS/82/2014-15); the old app.cpcbccr.com link serves an HTML page with third-party ads (likely no longer a CPCB site) - do not use it. C3 then checked in the official PDF: Table 3.12 "Health Statements for AQI Categories", printed p. 36 (PDF p. 38),
  Satisfactory "May cause minor breathing discomfort to sensitive people" -> C3 cites [1][2][3]. `backend/test_source_links.py` (5 checks, in-process) fails if
  "app.cpcbccr.com" appears in frontend files, served pages, /api/meta, /api/weekly, e-mail sources or the rule table, or as a URL in the docs.
  **Category statements aligned (26 Oct 2026):** `advice.IMPACT` = CPCB [1] Table 3.12 (p. 36) word for word for all six categories ("Minimal Impact"; Moderate
  "to the people ... asthma and discomfort"; Poor "... heart disease with short exposure"; Very Poor ". Effect may be ..."; Severe "respiratory effects ...
  lung/heart diseases. The health impacts may be experienced even during light physical activity"). Sources per category `advice.IMPACT_SRC`: [1][2] where
  Arthapedia is identical (Good, Satisfactory, Very Poor), else [1] only. Used by the advice card, Health advice tab, e-mails (headline) and the reference doc
  section 1; weekly S2 source note now quotes [1] exactly. Test `backend/test_category_statements.py` (7 checks, in-process).
  A10 verified in the ASHA handbook [3] (scanned PDF read page by page): printed p. 31, Chapter 03 table "AQI Levels, Health Effects and Protective Health Measures",
  Moderate / vulnerable "Ensure taking frequent water breaks between work" (air-pollution table, not heat advice) -> kept. Note under the chips: "Main pollutant =
  the pollutant with the highest CPCB sub-index on most days; the WHO column compares against stricter guideline levels." 33 rules; test_weekly.py 61 checks
  (N1-N4, U9). Test lesson: replay page tests must wait for the page's start-up jump (first weekly card drawn) before setting the hour.

## Readability redesign (26 Oct 2026; presentation only - NO wording changed)
- **Bold key phrases:** weekly rules carry `**...**` inside `text` in `weekly_advice_rules.json`; `weekly.py` strips them into `text` (plain, what every test
  and document compares) and keeps `marked`. Advice parts get `marked` from `advice.mark()` + the phrase list `advice.EMPHASIS` (the Python strings stay
  unchanged). Rendered as `<strong>` by `ui.js md()` and in the e-mail.
- **Summary first** (advice card, Health advice tab, pop-up, weekly card): category badge + status line, "Your top 3 actions" with icons (CSS masks
  `ic-mask|home|clock|doctor|medicine|walking|info`), then "Show all advice" (amber "May affect you", green "What you can do"; weekly also red
  "If this continues"; grey sources). Top 3 = `advice.top_actions`: up to 2 group lines (or "what to do"), best time, doctor (alert), tip; weekly
  `weekly.top3()` = profile's own actions first (response field `top3`). Section class is `asec` (`sec` was already the "Forecast" heading).
- **Weekly card:** donut "days per CPCB category" (+ grey hatched "No data"), centre "N of 7 days Moderate or worse", strip of 7 dots (oldest -> newest),
  pollutant table collapsed ("Show pollutant details").
- **"All stations now"** (`GET /api/stations/now?mode=replay&t=|live`; live stations now also return `aqi`/`category`): shell `frontend/stations.js`, view (a)
  `stations_each.js` ring gauges (default), view (b) `stations_bycat.js` donut by category; toggle remembered in localStorage `aqiStationsView`. Delete one
  file + its `<script>` tag to drop a view. Replay: clicking a station keeps the replay hour (`app.js switchStationKeepTime`). Live: stale (> 24 h) rings greyed
  "STALE · N h old" + red "DATA IS OLD" line.
- **E-mail:** `compose_alert` returns `MailText` (the plain text, a str) carrying `.html` (inline CSS, tables, no script/svg/style/class, ~13 KB);
  `build_message()` = text/plain + text/html. No PNG chart (optional; skipped).
- Test `backend/test_readability.py` (42 checks, port 8045/9345) incl. WCAG AA contrast and 390 px; screenshots `screenshots_preview/redesign/`.
- **Review fixes (26 Oct 2026):** the e-mail preview is generated from the REAL replay alert (`notify_email.replay_compose`, Silk Board label 24 Apr 01:00 =
  issued 02:00 hour ending, the test account's profile); test X1: e-mail text + HTML, pop-up and +6 h forecast card show identical AQI 256, range 249-290, Poor,
  PM2.5, target 08:00 (pop-up and forecast cards carry `data-aqi/category/range/dominant/target/horizon`). All shown times are HOUR-ENDING like the banner
  (`/api/weekly` window.clock_end, `/api/stations/now` clock_end; tests Y1 replay, Y2 live). Station tiles 132 px, names nowrap, no mid-word breaks (Range-based
  tests Z1 desktop, Z2 phone). Top 3: groups with IDENTICAL action text (+ source) merged into one line "Lung disease, heart disease: <unchanged action>"
  (`advice.merged_groups`, item carries `covers` = the single lines it replaces, so "Show all advice" / e-mail do not repeat them); tests T3, T7.
  User decision: keep BOTH stations views (toggle).

## Installable app (PWA) + Web Push channel (built 26 Oct 2026)
- `frontend/manifest.json` (name "AQ & Health Risk Framework", short "AQ Health", standalone, theme #0b3c5d, background #f4f6f9), generic "AQ" letter-mark
  icons `frontend/icons/` (192/512 any + maskable, apple-touch-icon 180, badge 96; made with Pillow), head tags on every page. `frontend/sw.js`
  (cache names *-v1: bump VERSION when un-versioned files such as fonts/icons change): static cache-first (links carry ?v=), pages network-first,
  ALL /api GET network-first with `X-AQI-Saved-At`; offline -> saved copy + `X-AQI-Offline` -> `ui.js setOffline` banner "Offline - showing data from
  <time>" (oldest copy on screen, numbers dimmed, never as current). Never cached: /api/auth/* except session, /api/me*, /api/push/*, /api/email/*,
  /api/profile, non-GET. "Install app" button in #acctNav (Android: beforeinstallprompt; iPhone: always the Safari steps dialog).
- Push channel `backend/notify_push.py` (pywebpush 2.5.0 installed in aqi env 26 Oct 2026; FakeWebPush under AQI_EMAIL_FAKE/AQI_PUSH_FAKE): table
  `push_subs` in users.db (per device: endpoint, p256dh, auth, live, replay, last; cascade on account delete), endpoints `/api/push/key`,
  `/api/me/push/subscribe|unsubscribe|status|test` (endpoint always in the POST body). Live: `notify_email._live_push` (shared 12 h cooldown,
  stale rule, sent mode 'live-push', own rate limit data/push_rate.json, failure isolation). Replay: `replay_enqueue_push` -> outbox channel "push"
  (mode 'replay-push'). 404/410 -> subscription deleted. Payload: "[REPLAY DEMO] <cat> · AQI <n> · <station>", body "Likely for the hour ending ...,
  issued ... <top action> [n] Not medical advice."; tap opens `/?station=&period=&at=<label>&pauseonalert=1` (app.js reads ?at=) or
  `/live.html?station=` (live.js reads ?station=). Log data/push_log.jsonl: user, sha256[:12] of endpoint, ok, status (never keys/endpoints/text).
- VAPID keys: `python backend\make_vapid_keys.py` (appends to .env only if missing; VAPID_SUBJECT=mailto:GMAIL_ADDRESS; private key never printed).
  NOT run by Claude: the user runs it.
- Tunnel safety (`app.is_local`): ?selftest login bypass and /api/scheduler/run-now only for direct local requests (no proxy headers); session +
  guest cookies Secure on https (uvicorn trusts X-Forwarded-Proto from 127.0.0.1), optional `AQI_ALLOWED_HOSTS` (TrustedHostMiddleware). README
  documents Cloudflare quick tunnel / ngrok and that quick-tunnel URLs change on every start (reinstall + re-subscribe).
- Tests `backend/test_pwa.py` (34 checks incl. Chrome `Page.getInstallabilityErrors` = [], offline reload with the server killed, stubbed browser
  PushManager for the profile switch; Lighthouse not installed, and its PWA category was removed in v12). Screenshots `screenshots_preview/pwa/`
  (home screen and notification are labelled mock-ups drawn from the real payload).

## Dark mode fixes (26 Oct 2026, user's Android phone in system dark theme)
- Cause: a blanket dark-theme rule gave EVERY button (except a few classes) dark navy text #082a42, so station tiles, the "Each station | By category"
  toggle, legend buttons, station links, tabs, "Install" and "Delete my account" became unreadable. Replaced by tokens `--on-primary` (white light /
  #082a42 dark) and `--on-muted`; no hard-coded dark text colours. Also: "Continue replay" and the active toggle use `--on-primary`, the "main" mark
  uses `--link`, the "Live data" dot #ff8f8f (5:1 on navy).
- "Install" button: solid white with navy text, drawn download icon (CSS mask `.ib-ico`, no font glyph -> no missing-glyph box), hidden in the installed
  app (`html.standalone` + `@media (display-mode: standalone)`).
- Notification badge: `frontend/icons/badge-96.png` is now a monochrome white "AQ" on transparent (Android draws the status-bar badge from alpha only;
  the old opaque icon showed as a white square). sw.js passes icon (colour) + badge; cache VERSION v2 so installed phones fetch the new file.
- Contrast scan for EVERY visible text: `backend/contrast_scan.py` (ALLTEXT_JS; skips gradient/image backgrounds, disabled controls and deliberately dimmed
  elements). test_readability.py "K" checks: replay (all tabs, both station views, all details), alert pop-up, install help, live, profile, signed-out pages
  in LIGHT and DARK (Emulation.setEmulatedMedia prefers-color-scheme), 1366 and 390 px: 0 failures (~6400 texts per mode/width). test_pwa.py D10b
  (offline banner dark), D12-D15 (install button, standalone, badge file, real push via DevTools ServiceWorker.deliverPushMessage -> icon + badge).
  Headless Chrome cannot emulate display-mode: D13 simulates navigator.standalone. Dark screenshots: screenshots_preview/redesign/dark/, pwa/*dark*.
- Profile text: "stored only on the computer running this app (not on this phone)".

## Limitations to state in the paper (live system)
- **Lead-time mismatch:** training weather comes from Open-Meteo's Historical Forecast API, which stitches the first hours of each
  model run (short lead). Live weather for +12..24 h is a true longer-lead forecast, so it is less accurate than the training weather.
- **Grid point vs station:** Open-Meteo returns the nearest ~2 km model grid cell (e.g. 12.8998, 77.6567, 884 m for Silk Board), not the
  station location.
- Weather check (2026-10-14, Open-Meteo minus station hourly, 2025-02 to 2026-10): Open-Meteo has 0% missing at all 8 stations.
  Open-Meteo wind (10 m) is +1.5..+3 m/s above station wind with low correlation (r 0.16-0.75); RH and temperature agree well at some
  stations (r ~0.9) and poorly at others (RH r = 0.27 Hebbal, 0.12 Ramanagara; temperature r = 0.48 Jayanagar, 0.60 Mysuru), which
  looks like station sensor problems (not verified). Station weather was used in the research results; live uses Open-Meteo.

## Related documents (Claude Docs, made in the earlier chat)
- How the CSH-AQI Model Works: https://claude.ai/code/artifact/f91fbf3a-0087-4761-942a-ed60e078c64a
- Health Advisory Reference Framework: https://claude.ai/code/artifact/48a7f617-ac18-4951-98e9-e9b6de07cbff
- CSH-AQI Literature Survey and Novelty Assessment: https://claude.ai/code/artifact/6655dbd7-7636-421a-9cc1-cea932fd7b64

## Dark theme "Direction D" for the website (31 Oct 2026; presentation only)
- Same look as the phone app (`mobile/`): one block at the END of `frontend/style.css` (selectors `:root:not(#_)` so it overrides the older light rules and
  the older prefers-color-scheme rules). Always dark. Tokens: bg #0b1320, surface #131c2b, surface-2 #1c2738, text #f2f5f9, muted #9aa8b8, accent #7cc4ff,
  CPCB colours brightened (#3fbf6f, #a8d64a, #f5c400, #ff8a2a, #d6363c, #a3262a). Primary buttons light with dark text. No ids, wording or logic changed.
- Chart colours (app.js, live.js) and Chart.js gridlines (ui.js) adjusted for the dark background. Asset links `?v=20261031a`, service-worker cache v3.
- Checked by screenshots only (replay page desktop + 390 px, login). The project's UI test suites were NOT re-run (FastAPI not installable in that session):
  re-run test_readability.py (contrast scan) and the other UI tests before relying on them.

## Phone app redesign v2.0 (4 Nov 2026; presentation only, all features kept)
- Warm minimalist + editorial design system in `mobile/src/theme.js` (tokens LIGHT ivory #f6f1e9 / DARK charcoal #121110, pastel
  tints, CPCB colours, Lora serif display + Inter, radii, shadows) and `mobile/src/ui.js` (Card, Btn, Chip, Segmented, Toggle, Orb =
  SVG lit sphere, Glow, Banner, ActionCard). Every text/background pair checked >= 4.5:1.
- Theme engine: localStorage `aqhealth.theme` = light | dark | system (default system). System uses `AQAndroid.systemDark()`
  (Android uiMode) or matchMedia; Android `onConfigurationChanged` calls `window.__aqSystemThemeChanged` so System follows the
  phone live; `AQAndroid.saveTheme` keeps it in SharedPreferences for start-up colours; `setSystemBars` colours status/nav bars.
  Switching reloads the WebView (tokens are read once). Header sun/moon button removed; control is Profile -> Appearance.
- Fonts: unmodified `Lora-Variable.ttf` (OFL with Reserved Font Name, so NOT subset) + Inter, in android assets `www/fonts`.
- Checked (scratchpad Playwright harness): 16 screens + 44 scroll views in both themes 0 low-contrast texts, 0 page errors; theme
  tests (default system, dark/light persist across restart, system follows live, Android config change); e-mail, rate limit,
  summary, share, listen regression all pass. Not built in Android Studio here (no SDK); Java compile-checked against stubs.
