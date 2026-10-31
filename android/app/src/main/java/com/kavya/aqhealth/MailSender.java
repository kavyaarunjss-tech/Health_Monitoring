package com.kavya.aqhealth;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.net.SocketTimeoutException;
import java.net.UnknownHostException;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.UUID;

import javax.net.ssl.SSLSocketFactory;

/**
 * Sends one e-mail through Gmail's SMTP server (smtp.gmail.com, port 465, SSL) from the phone itself.
 * No extra library: plain SMTP commands over an encrypted socket.
 *
 * Gmail needs an "App password" (16 letters, made at https://myaccount.google.com/apppasswords after turning on
 * 2-Step Verification). A normal Gmail password is refused by Google.
 *
 * The message is multipart/alternative: a plain-text part and an HTML part, both UTF-8, base64 encoded
 * (so any character, line length or a line with a single "." is safe).
 */
public final class MailSender {

    public static final String GMAIL_HOST = "smtp.gmail.com";
    public static final int GMAIL_PORT = 465;

    /** A failure with a message that can be shown to the user as it is. */
    public static class MailException extends Exception {
        public MailException(String message) {
            super(message);
        }
    }

    private MailSender() {
    }

    /** Sends through Gmail (SSL). */
    public static void sendGmail(String user, String appPassword, String to, String subject, String text, String html)
            throws MailException {
        send(GMAIL_HOST, GMAIL_PORT, true, user, appPassword, to, subject, text, html);
    }

    /** host/port/ssl are parameters only so that the code can be tested against a local test server. */
    public static void send(String host, int port, boolean ssl, String user, String password, String to,
                            String subject, String text, String html) throws MailException {
        user = clean(user);
        to = clean(to);
        password = password == null ? "" : password.replace(" ", "").trim();
        if (!looksLikeEmail(user)) {
            throw new MailException("The sending Gmail address is not set up (Profile → E-mail alerts).");
        }
        if (password.isEmpty()) {
            throw new MailException("The Gmail App password is missing (Profile → E-mail alerts).");
        }
        if (!looksLikeEmail(to)) {
            throw new MailException("Your e-mail address is missing or not valid.");
        }
        Socket socket = null;
        try {
            if (ssl) {
                socket = SSLSocketFactory.getDefault().createSocket();
            } else {
                socket = new Socket();
            }
            socket.connect(new InetSocketAddress(host, port), 15000);
            socket.setSoTimeout(20000);
            BufferedReader in = new BufferedReader(new InputStreamReader(socket.getInputStream(), StandardCharsets.UTF_8));
            OutputStream out = socket.getOutputStream();

            expect(in, 220, "The mail server did not answer.");
            command(out, "EHLO aqhealth.app");
            expect(in, 250, "The mail server refused the greeting.");
            command(out, "AUTH LOGIN");
            expect(in, 334, "The mail server does not accept a login.");
            command(out, base64(user.getBytes(StandardCharsets.UTF_8)));
            expect(in, 334, "The mail server refused the address.");
            command(out, base64(password.getBytes(StandardCharsets.UTF_8)));
            Reply login = read(in);
            if (login.code != 235) {
                throw new MailException("Gmail refused the login. Use a 16-letter App password (not your normal Gmail "
                        + "password) and check the Gmail address. Server said: " + login.code);
            }
            command(out, "MAIL FROM:<" + user + ">");
            expect(in, 250, "The mail server refused the sender.");
            command(out, "RCPT TO:<" + to + ">");
            expect(in, 250, "The mail server refused your e-mail address.");
            command(out, "DATA");
            expect(in, 354, "The mail server refused the message.");
            out.write(buildMessage(user, to, subject, text, html).getBytes(StandardCharsets.UTF_8));
            command(out, ".");
            expect(in, 250, "The mail server did not accept the message.");
            command(out, "QUIT");
        } catch (MailException e) {
            throw e;
        } catch (UnknownHostException e) {
            throw new MailException("No internet connection (could not find " + host + ").");
        } catch (SocketTimeoutException e) {
            throw new MailException("The mail server did not answer in time. Check the internet connection.");
        } catch (IOException e) {
            throw new MailException("Could not send the e-mail: no internet or the connection was blocked ("
                    + e.getClass().getSimpleName() + ").");
        } finally {
            if (socket != null) {
                try {
                    socket.close();
                } catch (IOException ignored) {
                    // closing anyway
                }
            }
        }
    }

    static String buildMessage(String from, String to, String subject, String text, String html) {
        String boundary = "aqh-" + UUID.randomUUID().toString().replace("-", "");
        SimpleDateFormat date = new SimpleDateFormat("EEE, dd MMM yyyy HH:mm:ss Z", Locale.US);
        StringBuilder m = new StringBuilder();
        m.append("From: AQ Health alerts <").append(from).append(">\r\n");
        m.append("To: <").append(to).append(">\r\n");
        m.append("Subject: ").append(encodeHeader(clean(subject))).append("\r\n");
        m.append("Date: ").append(date.format(new Date())).append("\r\n");
        m.append("Message-ID: <").append(UUID.randomUUID()).append("@aqhealth.app>\r\n");
        m.append("MIME-Version: 1.0\r\n");
        m.append("Content-Type: multipart/alternative; boundary=\"").append(boundary).append("\"\r\n\r\n");
        part(m, boundary, "text/plain", text == null ? "" : text);
        if (html != null && !html.isEmpty()) {
            part(m, boundary, "text/html", html);
        }
        m.append("--").append(boundary).append("--\r\n");
        return m.toString();
    }

    private static void part(StringBuilder m, String boundary, String type, String body) {
        m.append("--").append(boundary).append("\r\n");
        m.append("Content-Type: ").append(type).append("; charset=UTF-8\r\n");
        m.append("Content-Transfer-Encoding: base64\r\n\r\n");
        String b = base64(body.getBytes(StandardCharsets.UTF_8));
        for (int i = 0; i < b.length(); i += 76) {
            m.append(b, i, Math.min(b.length(), i + 76)).append("\r\n");
        }
    }

    /** RFC 2047 encoding for a subject with non-ASCII characters (e.g. "·" or "₂"). */
    static String encodeHeader(String s) {
        boolean ascii = true;
        for (int i = 0; i < s.length(); i++) {
            if (s.charAt(i) > 126) {
                ascii = false;
                break;
            }
        }
        return ascii ? s : "=?UTF-8?B?" + base64(s.getBytes(StandardCharsets.UTF_8)) + "?=";
    }

    /** Removes line breaks so a value can never add extra mail headers. */
    static String clean(String s) {
        return s == null ? "" : s.replace("\r", " ").replace("\n", " ").trim();
    }

    static boolean looksLikeEmail(String s) {
        return s != null && s.matches("[^@\\s<>]+@[^@\\s<>]+\\.[^@\\s<>]+");
    }

    private static void command(OutputStream out, String line) throws IOException {
        out.write((line + "\r\n").getBytes(StandardCharsets.UTF_8));
        out.flush();
    }

    private static final class Reply {
        final int code;
        final String text;

        Reply(int code, String text) {
            this.code = code;
            this.text = text;
        }
    }

    /** Reads a (possibly multi-line) SMTP reply such as "250-..." ... "250 ...". */
    private static Reply read(BufferedReader in) throws IOException {
        StringBuilder all = new StringBuilder();
        while (true) {
            String line = in.readLine();
            if (line == null) {
                throw new IOException("connection closed");
            }
            all.append(line).append('\n');
            if (line.length() < 4 || line.charAt(3) != '-') {
                int code;
                try {
                    code = Integer.parseInt(line.substring(0, Math.min(3, line.length())));
                } catch (NumberFormatException e) {
                    code = 0;
                }
                return new Reply(code, all.toString().trim());
            }
        }
    }

    private static void expect(BufferedReader in, int code, String problem) throws IOException, MailException {
        Reply r = read(in);
        if (r.code != code) {
            throw new MailException(problem + " (server said " + r.code + ")");
        }
    }

    // small base64 encoder (android.util.Base64 is not available in plain-Java tests; java.util.Base64 needs Android 8)
    private static final char[] B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/".toCharArray();

    static String base64(byte[] data) {
        StringBuilder sb = new StringBuilder((data.length + 2) / 3 * 4);
        for (int i = 0; i < data.length; i += 3) {
            int b0 = data[i] & 0xff;
            int b1 = i + 1 < data.length ? data[i + 1] & 0xff : 0;
            int b2 = i + 2 < data.length ? data[i + 2] & 0xff : 0;
            int n = (b0 << 16) | (b1 << 8) | b2;
            sb.append(B64[(n >> 18) & 63]).append(B64[(n >> 12) & 63]);
            sb.append(i + 1 < data.length ? B64[(n >> 6) & 63] : '=');
            sb.append(i + 2 < data.length ? B64[n & 63] : '=');
        }
        return sb.toString();
    }
}
