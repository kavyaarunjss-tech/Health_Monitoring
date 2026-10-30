# Integrated Air Quality & Health Risk Prediction Framework for Sustainable Urban Environments

Student research project (Karnataka, India). It forecasts the official **CPCB Air Quality Index (AQI)** 1 to 24 hours ahead for
8 KSPCB monitoring stations and turns the forecasts into **personalised, source-cited health alerts** on a local website.

## What it does
- **CSH-AQI model** (CPCB-Structured Hybrid): at forecast time most of each pollutant's CPCB averaging window is already measured, so the
  model forecasts only the unknown part with gradient boosting and rebuilds the AQI with the official CPCB formula (ensemble of 6 members).
  On the held-out test period it beats the persistence baseline at every horizon from +1 to +24 h (test MAE 0.65 / 3.22 / 5.32 / 9.05
  at +1 / +6 / +12 / +24 h vs persistence 1.09 / 4.84 / 7.13 / 9.59). Details: `CLAUDE.md`, `results/final/`.
- **Website** (FastAPI + plain HTML/JS): replay of a past period hour by hour (out-of-sample forecasts), live mode from OpenAQ data,
  user accounts with a health profile, personal advice (every health statement cites CPCB, MoHFW/NCDC or WHO; see
  `docs/health_advisory_reference.md`), alert pop-ups and per-user e-mail alerts.
- Not medical advice: a student research prototype.

## Folders
`model/` cleaning, CPCB AQI and the CSH-AQI model · `notebooks/` the research pipeline · `backend/` web server, data updater,
e-mail alerts, tests · `frontend/` website · `data/raw/` station exports (OpenAQ/KSPCB) · `results/` metrics and figures · `docs/` health
advisory reference.

## Install (Windows, Anaconda)
```
conda create -n aqi python=3.11
conda activate aqi
pip install -r requirements.txt
```

## Configure
Copy `.env.example` to `.env` in the project folder and fill in your own values (API keys, Gmail app password for e-mail alerts).
`.env` is git-ignored and must never be committed. The website runs without e-mail settings; e-mail alerts then stay off.

## WhatsApp alerts (optional, Twilio)

**Twilio trial accounts cannot send our alert text.** Checked 24 Oct 2026 on this project's trial account ("Try out WhatsApp", sender
+1 737 250 8034): free-form text is rejected with error 21654 even inside the 24-hour window; the Content API (to list or create templates)
answers error 20003 "not available on a Trial account"; Twilio's trial documentation allows only `To`, `From`, `ContentSid` (one of the
Twilio-provided templates on the Console's *Try out WhatsApp* page) and `statusCallback`, and says "You won't be able to write your own message".
So on a trial the only possible WhatsApp message is one of Twilio's fixed demo templates (set its id as `TWILIO_WA_CONTENT_SID` with
`TWILIO_WA_CONTENT_LAYOUT=none`); it cannot contain the station, AQI or advice.

For real AQI alerts by WhatsApp: upgrade the Twilio account, register a WhatsApp sender, run `python backend/create_wa_template.py --create`
(creates the UTILITY template "Air quality alert ({{4}}) for {{1}}: forecast {{2}} for the {{3}}. {{5}} Not medical advice; in an emergency
call 112." and requests WhatsApp approval), then set `TWILIO_WA_CONTENT_SID=HX...` and `TWILIO_WA_CONTENT_LAYOUT=aqi5`. Without a
`TWILIO_WA_CONTENT_SID` the app sends free-form text, which works only on senders that allow it (e.g. inside the 24-hour window on a
production sender).

Setup steps (sandbox / trial):
1. Create a free Twilio account (https://console.twilio.com) and open *Messaging > Try it out > Send a WhatsApp message* (the sandbox).
2. In `.env` set `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN` and `TWILIO_WHATSAPP_FROM=whatsapp:+17372508034` (the sandbox number).
   Never commit `.env`; the token is never printed or logged.
3. On the phone that should receive alerts, send `join twilio-trial` to **+1 737 250 8034** on WhatsApp.
4. On the website: *Profile* > *Alerts by WhatsApp*: enter the number in international format (e.g. `+919876543210`), tick live and/or
   replay-demo alerts, save, then press **Send test WhatsApp**. A few seconds later the page shows whether Twilio delivered it.

Sandbox limits: only the phone(s) that joined the sandbox receive messages, and only within 24 hours of their last message to the sandbox
number (otherwise Twilio error 63016; not joined = 63015; both are shown on the profile page). WhatsApp alerts follow the same rules as
e-mail alerts (Likely up to +24 h, Possible up to +12 h, 12 h cooldown shared by both channels, no live alerts on data older than 12 h,
never the same alert twice) and their own rate limit of 1 message per 60 s and 10 per hour. Messages are short plain text (under 600
characters, no links).

## Run the website
From the project folder, with the `aqi` environment active:
```
python backend/make_replay_data.py
python -m uvicorn backend.app:app --port 8000
```
Then open http://127.0.0.1:8000 (create an account, or use "Try the demo without an account").
`make_replay_data.py` builds `data/replay.db` from the official saved predictions (`results/final/csh_preds.pkl`, included) and only
needs to be run once. Live mode: `python backend/update_all.py` fetches the newest data; automatic hourly updates with
`$env:AQI_SCHEDULER="1"` (PowerShell) before starting the server.

## Phone app (PWA) and push notifications
The website can be installed on a phone like an app (name "AQ & Health Risk Framework", icon "AQ Health") and can send alerts as phone
notifications (Web Push), next to e-mail and WhatsApp. Same code, nothing to build.

1. Create the push keys once (adds `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY` and `VAPID_SUBJECT=mailto:<your GMAIL_ADDRESS>` to `.env`; the
   private key is never printed): `python backend\make_vapid_keys.py`. Keep them: new keys cancel every phone's subscription.
2. Restart the server. In your profile, "Alerts on this phone" has two switches (live / replay-demo alerts) for THIS device; the browser asks for
   permission once; "Send test notification" checks it.
3. Push alerts follow the same rules as e-mail and WhatsApp (Likely up to +24 h, Possible up to +12 h, one 12 h cooldown per station shared by all
   channels, no live alerts on data older than 12 h, never the same alert twice per channel) with their own rate limit (1 per 60 s, 10 per hour).
   The notification shows category, AQI, station, time and your top action; tapping it opens that alert. Replay ones start with "[REPLAY DEMO]".
   Subscriptions that the push service reports as expired (404 / 410) are deleted. `data/push_log.jsonl` keeps only time, user id, a short hash
   of the device, the result and the HTTP status: never keys, device addresses or text.
4. Offline: pages and data come from the server first; when the server cannot be reached the app shows the last saved copy with the banner
   "Offline - showing data from <time>" (never as current data).

### Phone testing over HTTPS (free tunnel)
Phones only install apps and accept push notifications from **https** sites (a laptop browser also allows http://localhost). A free tunnel gives the
local server a temporary https address. **The laptop and the server (and the tunnel window) must stay on**, and the laptop must not sleep.

Cloudflare quick tunnel (no account needed), in a second PowerShell window:
```
winget install --id Cloudflare.cloudflared
cloudflared tunnel --url http://localhost:8000
```
It prints an address like `https://random-words.trycloudflare.com`: open that on the phone. Start the server as usual, optionally with a host
allow-list so only your addresses are answered:
```
$env:AQI_ALLOWED_HOSTS="localhost,127.0.0.1,*.trycloudflare.com"; python -m uvicorn backend.app:app --port 8000
```
Alternative: ngrok (free account and authtoken; `ngrok http 8000`; add `*.ngrok-free.app` to `AQI_ALLOWED_HOSTS`). ngrok's free plan includes one
fixed address, which is better for a phone app: a Cloudflare quick tunnel gets a NEW address every time it starts, and an installed app and its
push subscription belong to one address (after a new address: open it, install again, switch "Alerts on this phone" on again).

What changes over https (automatic): the session and guest cookies are sent with `Secure` (always `HttpOnly` and `SameSite=Lax`; uvicorn trusts
the tunnel's `X-Forwarded-Proto` because the tunnel connects from 127.0.0.1); the "same site" check of every changing request uses the tunnel
address; links in e-mails (confirm address, reset password) use the address the request came from. Not available through the tunnel (only on the
laptop itself): the developer self-tests (`?selftest=...`) and "run update now".

### Install on the phone
- **Android (Chrome):** open the https address, log in, tap **Install app** at the top (or Chrome menu > Install app / Add to Home screen).
- **iPhone (Safari, iOS 16.4 or newer for notifications):** Share > Add to Home Screen > Add; open the app from the home screen and turn on
  "Alerts on this phone" there (iPhones send notifications only to installed apps).

## Reproduce the research results
The notebook `notebooks/CSH_AQI_hybrid_forecasting.ipynb` (run from the `notebooks/` folder) goes from the raw station files to the results.
The official run uses the script (about 80 min on a laptop), from the `model/` folder:
```
python -c "import pandas as pd; pd.read_csv('../data/processed/clean_hourly_all_stations.csv', parse_dates=['datetime']).to_pickle('../data/processed/clean_hourly_all_stations.pkl')"
python run_final.py ../data/processed/clean_hourly_all_stations.pkl ../results/final/csh
```

## Tests
Each test starts its own server on a test port and never sends real e-mail, WhatsApp or push notifications, e.g. `python backend/test_accounts.py`,
`python backend/test_advice.py`, `python backend/test_pwa.py`; the browser tests need Google Chrome.

## Data and licences
Station data: KSPCB stations via [OpenAQ](https://openaq.org) (CC BY 4.0); weather: [Open-Meteo](https://open-meteo.com).
Font: Inter, SIL Open Font License 1.1 (`frontend/fonts/OFL.txt`). Chart.js (MIT) in `frontend/vendor/`.
