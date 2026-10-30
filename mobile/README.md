# AQ Health: phone app

Android (and iPhone) app for the Integrated Air Quality and Health Risk Prediction Framework.
Built with Expo / React Native. It runs inside the free **Expo Go** app, so Android Studio is not needed.

All data, forecasts and health advice come from the project's backend on the laptop (`backend/app.py`).
The app adds phone screens, the replay player, alert pop-ups and phone notifications.

## Screens
- **Home**: current AQI with CPCB colour, forecasts for +1, +6, +12 and +24 h with likely ranges, a 24 h chart, your top 3 actions, pollutants.
  Replay controls: Play / Pause, -1 h / +1 h, speed, "Skip to next pollution event".
- **Advice**: personal health advice for your profile, with sources [1]-[7] and the disclaimer.
- **Stations**: all 8 stations at a glance; tap one to follow it.
- **Week**: the last 7 days, the trend and weekly health advice.
- **Profile**: name, station, health groups, alert level, notifications, replay period, laptop server address.
- **Alerts**: when a forecast reaches your alert level, the replay pauses, a pop-up shows the forecast and advice, and the phone shows a notification.

## Run it (Windows, project in C:\aqi)

**One time:** install Node.js LTS from https://nodejs.org. On the phone, install **Expo Go** from the Play Store.

**Terminal 1** (project folder), start the backend so the phone can reach it:
```powershell
.venv\Scripts\python.exe -m uvicorn backend.app:app --host 0.0.0.0 --port 8000
```
If Windows Firewall asks, tick **Private networks** and click **Allow**.

**Terminal 2**, first time only:
```powershell
cd mobile
```
```powershell
npm.cmd install expo@latest
```
```powershell
npx.cmd expo install react react-native expo-status-bar expo-constants expo-notifications @react-native-async-storage/async-storage react-native-safe-area-context
```
Then every time:
```powershell
npx.cmd expo start
```
Scan the QR code with Expo Go. Phone and laptop must be on the **same Wi-Fi**, or connect the laptop to the phone's hotspot (college Wi-Fi often blocks this).

In the app: the laptop address is filled in automatically. Tap **Test connection**, then **Start**.

## Problems
- *"Cannot reach the server"*: terminal 1 must be running with `--host 0.0.0.0`; check the address in Profile (find the laptop's IPv4 address with `ipconfig`); allow Python in Windows Firewall; use the phone hotspot.
- *"Project is incompatible with this version of Expo Go"*: run `npm.cmd install expo@latest` and `npx.cmd expo install --fix`, then start again.
- *QR code does not connect*: `npx.cmd expo start --tunnel` (the backend address must still be the laptop's IP on the same network).
- Live mode needs `data/aqi.db` (built by `backend/update_all.py` with the OpenAQ key). Without it the app says so; the Replay demo always works.

## Real installable APK (optional, later)
`npx.cmd eas-cli build -p android --profile preview` builds an APK in Expo's cloud (free Expo account needed); the link it prints installs the app on any Android phone.
