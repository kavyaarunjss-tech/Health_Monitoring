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
