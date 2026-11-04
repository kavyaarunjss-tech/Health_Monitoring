# AQ Health: Android Studio project

Native Android app (Java) for the Integrated Air Quality and Health Risk Prediction Framework.
The screens are the same tested app code as `../mobile`, built into `app/src/main/assets/www` and shown in a WebView.

**Works without the laptop:** real forecasts, alerts and health advice from the project are built in
(replay 22–25 Apr 2026, all 8 stations, each health group). Switch "Use built-in demo data" off in
Profile (gear icon) to read from the laptop backend instead.

## Run in Android Studio
1. Install Android Studio (https://developer.android.com/studio). On first start let it install the Android SDK.
2. **File → Open** → select this `android` folder → **Trust project**. Wait for "Gradle sync" to finish
   (first time 5–15 minutes; it downloads Gradle and the Android build tools).
   If it asks to upgrade the Android Gradle Plugin, you may click **Upgrade** or ignore it.
3. Run on your phone: on the phone enable **Developer options → USB debugging**
   (Settings → About phone → tap *Build number* 7 times), connect by USB, allow the prompt,
   pick the phone in the device list at the top and press the green **Run ▶** button.
   Or run on an emulator: **Device Manager → Create device → Pixel → Next → Finish**, then **Run ▶**.
4. Allow notifications when the app asks.

## E-mail alerts (sent by the phone through Gmail)
The phone itself sends the e-mails, so the laptop server is **not** needed, but the phone needs internet.
1. Make a Gmail **App password** for the account that will send the alerts (your own Gmail is fine):
   turn on **2-Step Verification** in your Google account, open https://myaccount.google.com/apppasswords,
   create one named "AQ Health" and copy the 16 letters. (Your normal Gmail password does not work.)
2. In the app open **Profile (gear icon) → E-mail alerts**:
   - **Your e-mail**: where alerts and summaries arrive.
   - **Sending Gmail account**: the Gmail address and its App password → **Save sending account**.
   - Tap **Send test e-mail** and check the inbox (look in Spam the first time).
   - Switch on **E-mail me air quality alerts**, then press **Save** at the bottom.
3. Press **Play** on Home: every alert now also arrives as an e-mail (forecast, your personal advice with sources,
   disclaimer). Replay alerts are marked **[REPLAY DEMO]**. At most one e-mail per minute; the same alert is never
   sent twice (also after rewinding). **E-mail me a health summary now** sends the current AQI, the next 24 h,
   your top actions and this week's summary.

The App password is kept only in this app's private storage on the phone (not in the app's web data, not backed up),
and is never shown again. **Remove sending account** deletes it.

## Other features
- **Design (v2.1):** soft wellness look. White cards on a soft white page with blurred colour glows (light), near-black layered
  surfaces with dimmed glows (dark); one clean sans-serif font (Inter); a soft glow in the CPCB category colour behind the AQI;
  floating station pill, tab bar and replay player; Listen and Share as round buttons on the AQI card.
- **Appearance:** Profile (avatar, top right) → Appearance → **Light / Dark / System**. System follows the phone's dark-mode
  setting and switches by itself when the phone changes. The choice is saved on the phone. Switching restarts the replay.
- **Listen:** the phone reads the current air, forecast and your top actions aloud (Home), or the alert (alert screen).
  Uses the phone's text-to-speech voice (Indian English if installed). If nothing is heard, check the media volume
  and that "Speech Services by Google" is installed.
- **Share:** sends today's AQI, the 24 h forecast and one tip to WhatsApp, Gmail, SMS etc.

## Make an APK to install on any phone
**Build → Build App Bundle(s) / APK(s) → Build APK(s)**, then click **locate** in the popup.
The file is `app/build/outputs/apk/debug/app-debug.apk`. Send it to the phone (USB, Drive, WhatsApp to yourself)
and open it; allow "install unknown apps" if asked.

## Demo
Profile: pick a health group (e.g. Lung disease) → Start → press **Play** on Home. Within a few seconds an
air quality alert appears for Silk Board (phone notification + full-screen alert). **Next event** jumps to
6 hours before the next pollution event.

## Rebuilding the screens after changing ../mobile
`cd ui-build`, `npm install esbuild react@19 react-dom@19`, `sh build.sh` (writes `app/src/main/assets/www/app.js`).
