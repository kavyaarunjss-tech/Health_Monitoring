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
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
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

/**
 * AQ Health: phone app for the Integrated Air Quality and Health Risk Prediction Framework.
 * The screens are the same app code as the Expo app (../mobile), built into assets/www and shown in a WebView.
 * The JavaScript side talks to Android through the "AQAndroid" bridge:
 *  - readAsset: built-in demo data (real backend responses, 22-25 Apr 2026, all 8 stations)
 *  - http:      requests to the laptop backend (when "built-in demo data" is switched off)
 *  - showAlert: phone notifications for air quality alerts
 *  - openUrl:   source links open in the phone's browser
 */
public class MainActivity extends Activity {

    private static final String CHANNEL_ID = "aq_alerts";
    private static final String START_PAGE = "file:///android_asset/www/index.html";

    private WebView web;
    private final Handler mainThread = new Handler(Looper.getMainLooper());
    private int notificationId = 1;

    @SuppressLint("SetJavaScriptEnabled")
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        createNotificationChannel();
        askNotificationPermission();

        web = new WebView(this);
        web.setBackgroundColor(Color.parseColor("#0B1320"));
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

    @Override
    protected void onDestroy() {
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
