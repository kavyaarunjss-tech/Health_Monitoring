package com.kavya.aqhealth;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.ActivityNotFoundException;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.content.res.Configuration;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.View;
import android.view.Window;
import android.speech.tts.TextToSpeech;
import android.webkit.JavascriptInterface;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.Locale;

/**
 * AQ Health: phone app for the Integrated Air Quality and Health Risk Prediction Framework.
 * The screens are the same app code as the Expo app (../mobile), built into assets/www and shown in a WebView.
 * The JavaScript side talks to Android through the "AQAndroid" bridge:
 *  - readAsset: built-in demo data (real backend responses, 22-25 Apr 2026, all 8 stations)
 *  - http:      requests to the laptop backend (when "built-in demo data" is switched off)
 *  - showAlert: phone notifications for air quality alerts
 *  - openUrl:   source links open in the phone's browser
 *  - mail*:     e-mail alerts sent from the phone through Gmail (MailSender). The sending Gmail address and its App
 *               password are kept in this app's private storage on the phone; the JavaScript side can save or remove
 *               them but never reads the password back.
 */
public class MainActivity extends Activity {

    private static final String CHANNEL_ID = "aq_alerts";
    private static final String START_PAGE = "file:///android_asset/www/index.html";
    private static final String MAIL_PREFS = "mail_sender";
    private static final String UI_PREFS = "ui";

    private WebView web;
    private final Handler mainThread = new Handler(Looper.getMainLooper());
    private int notificationId = 1;
    private TextToSpeech tts;
    private boolean ttsReady = false;

    @SuppressLint("SetJavaScriptEnabled")
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        createNotificationChannel();
        askNotificationPermission();

        tts = new TextToSpeech(this, status -> {
            if (status == TextToSpeech.SUCCESS && tts != null) {
                int r = tts.setLanguage(new Locale("en", "IN"));          // Indian English voice if installed
                if (r == TextToSpeech.LANG_MISSING_DATA || r == TextToSpeech.LANG_NOT_SUPPORTED) {
                    tts.setLanguage(Locale.ENGLISH);
                }
                tts.setSpeechRate(0.95f);
                ttsReady = true;
            }
        });

        web = new WebView(this);
        // start in the right colours (no dark flash in light mode): saved choice, or the phone's setting
        String startBg = startDark() ? "#0E0F12" : "#F6F7F9";
        getWindow().getDecorView().setBackgroundColor(Color.parseColor(startBg));
        applySystemBars(startBg, !startDark());
        web.setBackgroundColor(Color.parseColor(startBg));
        WebSettings settings = web.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);   // the app saves your profile in local storage
        settings.setAllowFileAccess(true);
        settings.setTextZoom(100);
        web.addJavascriptInterface(new Bridge(), "AQAndroid");
        web.setWebChromeClient(new WebChromeClient());
        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri uri = request.getUrl();
                if ("file".equals(uri.getScheme())) {
                    return false;
                }
                openExternal(uri.toString());
                return true;
            }
        });
        setContentView(web);

        if (savedInstanceState != null) {
            web.restoreState(savedInstanceState);
        } else {
            web.loadUrl(START_PAGE);
        }
    }

    @Override
    protected void onSaveInstanceState(Bundle outState) {
        super.onSaveInstanceState(outState);
        if (web != null) {
            web.saveState(outState);
        }
    }

    // ------------------------------------------------------------------ theme (Light / Dark / System)
    private boolean phoneIsDark() {
        int mode = getResources().getConfiguration().uiMode & Configuration.UI_MODE_NIGHT_MASK;
        return mode == Configuration.UI_MODE_NIGHT_YES;
    }

    private boolean startDark() {
        String m = getSharedPreferences(UI_PREFS, Context.MODE_PRIVATE).getString("theme", "system");
        if ("light".equals(m)) {
            return false;
        }
        if ("dark".equals(m)) {
            return true;
        }
        return phoneIsDark();
    }

    @SuppressWarnings("deprecation")
    private void applySystemBars(String hex, boolean lightBars) {
        try {
            int color = Color.parseColor(hex);
            Window w = getWindow();
            w.setStatusBarColor(color);
            w.setNavigationBarColor(color);
            View d = w.getDecorView();
            int flags = d.getSystemUiVisibility();
            if (Build.VERSION.SDK_INT >= 23) {
                flags = lightBars ? (flags | View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR) : (flags & ~View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR);
            }
            if (Build.VERSION.SDK_INT >= 26) {
                flags = lightBars ? (flags | View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR) : (flags & ~View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR);
            }
            d.setSystemUiVisibility(flags);
            d.setBackgroundColor(color);
        } catch (IllegalArgumentException ignored) {
            // not a colour
        }
    }

    /** The phone switched between light and dark (the activity is not restarted: configChanges includes uiMode). */
    @Override
    public void onConfigurationChanged(Configuration newConfig) {
        super.onConfigurationChanged(newConfig);
        if (web != null) {
            web.evaluateJavascript("window.__aqSystemThemeChanged && window.__aqSystemThemeChanged()", null);
        }
    }

    @Override
    protected void onDestroy() {
        if (tts != null) {
            tts.stop();
            tts.shutdown();
            tts = null;
        }
        if (web != null) {
            web.destroy();
        }
        super.onDestroy();
    }

    // ------------------------------------------------------------------ notifications
    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= 26) {
            NotificationChannel channel = new NotificationChannel(CHANNEL_ID, getString(R.string.channel_name),
                    NotificationManager.IMPORTANCE_HIGH);
            channel.setDescription("Forecast air quality reaches your alert level");
            channel.enableVibration(true);
            NotificationManager nm = getSystemService(NotificationManager.class);
            if (nm != null) {
                nm.createNotificationChannel(channel);
            }
        }
    }

    private void askNotificationPermission() {
        if (Build.VERSION.SDK_INT >= 33
                && checkSelfPermission("android.permission.POST_NOTIFICATIONS") != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{"android.permission.POST_NOTIFICATIONS"}, 1);
        }
    }

    @SuppressWarnings("deprecation")
    private void showNotification(String title, String body) {
        NotificationManager nm = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
        if (nm == null) {
            return;
        }
        Intent open = new Intent(this, MainActivity.class);
        open.setFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        PendingIntent pending = PendingIntent.getActivity(this, 0, open,
                PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        Notification.Builder builder = Build.VERSION.SDK_INT >= 26
                ? new Notification.Builder(this, CHANNEL_ID)
                : new Notification.Builder(this);
        builder.setSmallIcon(R.drawable.ic_stat_aq)
                .setContentTitle(title)
                .setContentText(body)
                .setStyle(new Notification.BigTextStyle().bigText(body))
                .setAutoCancel(true)
                .setContentIntent(pending);
        if (Build.VERSION.SDK_INT < 26) {
            builder.setPriority(Notification.PRIORITY_HIGH);
            builder.setDefaults(Notification.DEFAULT_ALL);
        }
        nm.notify(notificationId++, builder.build());
    }

    private void openExternal(String url) {
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url)));
        } catch (ActivityNotFoundException ignored) {
            // no browser installed
        }
    }

    private static String readAll(InputStream in) throws IOException {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        byte[] buffer = new byte[65536];
        int n;
        while ((n = in.read(buffer)) > 0) {
            out.write(buffer, 0, n);
        }
        return new String(out.toByteArray(), StandardCharsets.UTF_8);
    }

    // ------------------------------------------------------------------ bridge used by the app's JavaScript
    private class Bridge {

        @JavascriptInterface
        public String readAsset(String path) {
            try (InputStream in = getAssets().open(path)) {
                return readAll(in);
            } catch (IOException e) {
                return "null";
            }
        }

        @JavascriptInterface
        public void showAlert(final String title, final String body) {
            mainThread.post(() -> showNotification(title, body));
        }

        @JavascriptInterface
        public void openUrl(final String url) {
            mainThread.post(() -> openExternal(url));
        }

        // ---------------------------------------------------------- theme
        @JavascriptInterface
        public boolean systemDark() {
            return phoneIsDark();
        }

        @JavascriptInterface
        public void saveTheme(String mode) {
            String m = "light".equals(mode) || "dark".equals(mode) ? mode : "system";
            getSharedPreferences(UI_PREFS, Context.MODE_PRIVATE).edit().putString("theme", m).apply();
        }

        @JavascriptInterface
        public void setSystemBars(final String hex, final boolean lightBars) {
            mainThread.post(() -> applySystemBars(hex, lightBars));
        }

        // ---------------------------------------------------------- share and read aloud
        /** Opens the phone's share sheet (WhatsApp, Gmail, SMS, ...) with plain text. */
        @JavascriptInterface
        public void share(final String subject, final String text) {
            mainThread.post(() -> {
                Intent send = new Intent(Intent.ACTION_SEND);
                send.setType("text/plain");
                send.putExtra(Intent.EXTRA_SUBJECT, subject == null ? "" : subject);
                send.putExtra(Intent.EXTRA_TEXT, text == null ? "" : text);
                try {
                    startActivity(Intent.createChooser(send, "Share air quality"));
                } catch (ActivityNotFoundException ignored) {
                    // no app can share text
                }
            });
        }

        /** Reads text aloud with the phone's text-to-speech voice; returns false if no voice is available. */
        @JavascriptInterface
        public boolean speak(final String text) {
            if (!ttsReady || tts == null) {
                return false;
            }
            mainThread.post(() -> {
                if (tts != null) {
                    tts.speak(text == null ? "" : text, TextToSpeech.QUEUE_FLUSH, null, "aq");
                }
            });
            return true;
        }

        @JavascriptInterface
        public void stopSpeaking() {
            mainThread.post(() -> {
                if (tts != null) {
                    tts.stop();
                }
            });
        }

        @JavascriptInterface
        public boolean isSpeaking() {
            return tts != null && tts.isSpeaking();
        }

        // ---------------------------------------------------------- e-mail
        private SharedPreferences mailPrefs() {
            return getSharedPreferences(MAIL_PREFS, Context.MODE_PRIVATE);
        }

        /** {"configured": true/false, "sender": "x@gmail.com"}; the password is never returned. */
        @JavascriptInterface
        public String mailStatus() {
            SharedPreferences p = mailPrefs();
            String user = p.getString("user", "");
            boolean ok = !user.isEmpty() && !p.getString("pass", "").isEmpty();
            try {
                return new JSONObject().put("configured", ok).put("sender", user).toString();
            } catch (Exception e) {
                return "{\"configured\":false,\"sender\":\"\"}";
            }
        }

        /** Saves the sending Gmail address and its App password; returns "" or an error message. */
        @JavascriptInterface
        public String saveMailSender(String user, String appPassword) {
            String u = MailSender.clean(user).toLowerCase(java.util.Locale.ROOT);
            String pw = appPassword == null ? "" : appPassword.replace(" ", "").trim();
            if (!MailSender.looksLikeEmail(u)) {
                return "Enter the Gmail address that will send the alerts.";
            }
            if (pw.length() != 16) {
                return "A Gmail App password has 16 letters (spaces do not matter). Your normal Gmail password will not work.";
            }
            mailPrefs().edit().putString("user", u).putString("pass", pw).apply();
            return "";
        }

        @JavascriptInterface
        public void clearMailSender() {
            mailPrefs().edit().clear().apply();
        }

        /** Sends in the background; the result arrives as window.__aqMailDone(id, ok, message). */
        @JavascriptInterface
        public void sendMail(final int id, final String to, final String subject, final String text, final String html) {
            final SharedPreferences p = mailPrefs();
            new Thread(() -> {
                boolean ok;
                String message;
                try {
                    MailSender.sendGmail(p.getString("user", ""), p.getString("pass", ""), to, subject, text, html);
                    ok = true;
                    message = "E-mail sent to " + MailSender.clean(to);
                } catch (MailSender.MailException e) {
                    ok = false;
                    message = e.getMessage();
                } catch (Exception e) {
                    ok = false;
                    message = "Could not send the e-mail (" + e.getClass().getSimpleName() + ").";
                }
                final String js = "window.__aqMailDone && window.__aqMailDone(" + id + "," + ok + "," + JSONObject.quote(message) + ")";
                mainThread.post(() -> {
                    if (web != null) {
                        web.evaluateJavascript(js, null);
                    }
                });
            }).start();
        }

        @JavascriptInterface
        public void http(final int id, final String url, final String method, final String body) {
            new Thread(() -> {
                int status = 0;
                String text = "";
                HttpURLConnection conn = null;
                try {
                    conn = (HttpURLConnection) new URL(url).openConnection();
                    conn.setConnectTimeout(8000);
                    conn.setReadTimeout(15000);
                    conn.setRequestMethod(method == null || method.isEmpty() ? "GET" : method);
                    if (body != null && !body.isEmpty() && !"GET".equals(method)) {
                        conn.setDoOutput(true);
                        conn.setRequestProperty("Content-Type", "application/json");
                        try (OutputStream os = conn.getOutputStream()) {
                            os.write(body.getBytes(StandardCharsets.UTF_8));
                        }
                    }
                    status = conn.getResponseCode();
                    InputStream in = status >= 400 ? conn.getErrorStream() : conn.getInputStream();
                    text = in == null ? "" : readAll(in);
                } catch (Exception e) {
                    status = 0;
                    text = "";
                } finally {
                    if (conn != null) {
                        conn.disconnect();
                    }
                }
                final String js = "window.__aqNetDone(" + id + "," + status + "," + JSONObject.quote(text) + ")";
                mainThread.post(() -> {
                    if (web != null) {
                        web.evaluateJavascript(js, null);
                    }
                });
            }).start();
        }
    }
}
