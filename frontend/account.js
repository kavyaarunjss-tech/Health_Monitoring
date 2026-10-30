/* Account pages: sign-up, login, profile, forgot password, reset password. Plain JavaScript.
   The session is an HTTP-only cookie set by the server; this script never sees the session token or stores the password. */
"use strict";
const A$ = (id) => el(id);                 // guarded lookup (ui.js): never null
const DEFAULT_ALERT_A = { vulnerable: 101, healthy: 201 };

async function send(method, path, body) {
  const r = await apiFetch(path, { method, headers: { "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body),
                                   credentials: "same-origin" });
  let j = null; try { j = await r.json(); } catch (e) { /* ignore */ }
  if (!r.ok) { const err = new Error((j && j.detail && typeof j.detail === "string") ? j.detail : "Please check the form (HTTP " + r.status + ")."); err.status = r.status; throw err; }
  return j;
}
function say(id, text, kind) { const el = A$(id); el.textContent = text; el.className = "msg " + (kind || ""); }
function busy(form, on) { form.querySelectorAll("button, input, select").forEach((x) => { x.disabled = on; }); }
function next() {                       // only our own two pages; never an external URL
  const n = new URLSearchParams(location.search).get("next") || "";
  return n === "/live.html" ? n : "/";
}
function bindShowPassword() {
  document.querySelectorAll("[data-toggle-pw]").forEach((cb) => {
    cb.onchange = () => document.querySelectorAll("input[data-pw]").forEach((i) => { i.type = cb.checked ? "text" : "password"; });
  });
}

/* logged-in users skip the login and sign-up pages */
async function skipIfLoggedIn() {
  const me = await getAccount();
  if (me) { location.replace(next()); return true; }
  return false;
}

/* ---------- sign-up ---------- */
async function pageSignup() {
  if (await skipIfLoggedIn()) return;
  const opt = await send("GET", "/api/account/options");
  A$("pwHint").textContent = "At least " + opt.min_password + " characters.";
  const f = A$("signupForm");
  f.onsubmit = async (e) => {
    e.preventDefault();
    if (A$("password").value !== A$("password2").value) { say("msg", "The two passwords are not the same.", "err"); A$("password2").focus(); return; }
    if (!A$("consent").checked) { say("msg", "Please tick the consent box to create an account.", "err"); return; }
    busy(f, true); say("msg", "Creating your account...");
    try {
      await send("POST", "/api/auth/signup", { name: A$("name").value, email: A$("email").value, password: A$("password").value, consent: true });
      location.href = "/profile.html?welcome=1";
    } catch (err) { say("msg", err.message, "err"); busy(f, false); }
  };
}

/* ---------- login ---------- */
async function pageLogin() {
  if (await skipIfLoggedIn()) return;
  const f = A$("loginForm");
  const nx = next();
  if (new URLSearchParams(location.search).has("next")) A$("why").hidden = false;
  A$("guestLink").href = nx === "/live.html" ? "/live.html?guest=1" : "/?guest=1";
  if (new URLSearchParams(location.search).get("reset") === "1") say("msg", "Your password was changed. Please log in with the new password.", "ok");
  f.onsubmit = async (e) => {
    e.preventDefault();
    busy(f, true); say("msg", "Logging in...");
    try {
      await send("POST", "/api/auth/login", { email: A$("email").value, password: A$("password").value });
      location.href = next();
    } catch (err) { say("msg", err.message, "err"); busy(f, false); A$("password").select(); }
  };
}

/* ---------- forgot / reset password ---------- */
async function pageForgot() {
  const f = A$("forgotForm");
  f.onsubmit = async (e) => {
    e.preventDefault();
    busy(f, true);
    try {
      const r = await send("POST", "/api/auth/forgot", { email: A$("email").value });
      say("msg", r.email_configured ? r.message : "E-mail sending is not configured on this computer, so no reset link can be sent. Ask the project owner.", r.email_configured ? "ok" : "err");
    } catch (err) { say("msg", err.message, "err"); }
    busy(f, false);
  };
}
async function pageReset() {
  const token = new URLSearchParams(location.search).get("token") || "";
  const f = A$("resetForm");
  if (!token) { say("msg", "This page needs the link from the reset e-mail.", "err"); busy(f, true); return; }
  f.onsubmit = async (e) => {
    e.preventDefault();
    if (A$("password").value !== A$("password2").value) { say("msg", "The two passwords are not the same.", "err"); return; }
    busy(f, true);
    try { await send("POST", "/api/auth/reset", { token, password: A$("password").value }); location.href = "/login.html?reset=1"; }
    catch (err) { say("msg", err.message, "err"); busy(f, false); }
  };
}

/* ---------- profile ---------- */
let OPT = null, ME = null;
function formGroups() {          // the same rules as the server (users.py): ticked conditions + age < 14 child, age >= 60 older adult
  const conds = Array.from(document.querySelectorAll("input[name=cond]:checked")).map((x) => x.value);
  const ageTxt = A$("age").value.trim(), age = ageTxt === "" ? null : +ageTxt;
  const auto = [];
  if (age != null && Number.isInteger(age) && age < OPT.child_under) auto.push("child");
  if (age != null && Number.isInteger(age) && age >= OPT.older_from) auto.push("older");
  return { conds, auto, groups: conds.concat(auto), age };
}
function renderDerived() {
  const g = formGroups();
  const dflt = g.groups.length ? DEFAULT_ALERT_A.vulnerable : DEFAULT_ALERT_A.healthy;
  A$("autoGroups").innerHTML = g.auto.length
    ? "Added automatically from your age: <b>" + g.auto.map((x) => GROUP_LABEL[x]).join(", ") + "</b>."
    : "No group is added from your age (child: under " + OPT.child_under + "; older adult: " + OPT.older_from + " or over).";
  A$("groupsUsed").textContent = g.groups.length ? "Advice and alerts use: " + g.groups.map((x) => GROUP_LABEL[x]).join(", ") + " (vulnerable profile)."
                                                  : "Advice and alerts use: healthy adult (general population).";
  const sel = A$("alertFrom"), keep = sel.value;
  sel.innerHTML = "";
  const o0 = document.createElement("option"); o0.value = ""; o0.textContent = "Default for your profile: AQI " + dflt; sel.appendChild(o0);
  OPT.alert_choices.filter((v) => v < dflt).forEach((v) => { const o = document.createElement("option"); o.value = v; o.textContent = "AQI " + v + " (earlier than the default)"; sel.appendChild(o); });
  sel.value = Array.from(sel.options).some((o) => o.value === keep) ? keep : "";
  A$("alertInfo").textContent = (g.groups.length ? "Vulnerable profile: advice from AQI 51, alert from AQI 101 by default."
    : "Healthy adult: advice from AQI 101, alert from AQI 201 by default.") + " You may choose an earlier (lower) alert level, never a higher one. Everyone is alerted from AQI 301.";
}
function fillProfile(me) {
  ME = me;
  A$("pName").value = me.name;
  A$("pEmail").textContent = me.email;
  A$("verified").innerHTML = me.email_verified ? "<span class='badge ok'>Confirmed</span>" : "<span class='badge warn'>Not confirmed yet</span>";
  A$("sendVerify").hidden = me.email_verified;
  A$("age").value = me.age == null ? "" : me.age;
  A$("station").value = me.station;
  document.querySelectorAll("input[name=cond]").forEach((cb) => { cb.checked = me.conditions.includes(cb.value); });
  renderDerived();
  A$("alertFrom").value = me.alert_from == null ? "" : String(me.alert_from);
  if (A$("alertFrom").value !== (me.alert_from == null ? "" : String(me.alert_from))) A$("alertFrom").value = "";
  A$("emailAlerts").checked = me.email_alerts;
  A$("replayEmails").checked = me.replay_emails;
  const notes = [];
  if (!me.email_configured) notes.push("E-mail sending is not configured on this computer (.env), so no e-mails can be sent yet.");
  else if (!me.email_verified) notes.push("Alert e-mails are sent only after you confirm your address (link in the e-mail we sent).");
  notes.push("Live alert e-mails are paused while your station's newest data is older than 12 hours.");
  A$("emailNote").textContent = notes.join(" ");
  // WhatsApp channel
  A$("waNumber").value = me.whatsapp || "";
  A$("waAlerts").checked = !!me.whatsapp_alerts;
  A$("waReplay").checked = !!me.replay_whatsapp;
  renderWaLast(me);
}
const E164_RE = /^\+[1-9]\d{7,14}$/;
const waNorm = (s) => String(s || "").replace(/[\s\-().]/g, "");
function renderWaLast(me) {                  // last WhatsApp delivery result (stored by the server after Twilio's status check)
  const el = A$("waLast"), w = me.wa_last;
  if (!me.whatsapp_configured) { el.className = "small muted"; el.textContent = "WhatsApp is not configured on this computer (.env), so no WhatsApp messages can be sent yet."; return; }
  if (!w) { el.className = "small muted"; el.textContent = ""; return; }
  const when = String(w.time || "").replace("T", " ").slice(0, 16);
  if (!w.ok && +w.code === 21654) {          // Twilio trial: only pre-approved templates -> an account limit, not a delivery error
    el.className = "small muted wa-trial"; el.textContent = "WhatsApp needs a paid Twilio account to send our alert text (last attempt " + when + ")."; return;
  }
  if (w.ok) { el.className = "msg small ok"; el.textContent = "Last WhatsApp message (" + (w.kind || "alert") + ", " + when + "): accepted / delivered."; }
  else { el.className = "msg small err"; el.textContent = "Last WhatsApp delivery failed: " + (w.code ? w.code + ": " : "") + (w.reason || "unknown reason") + " (" + when + ")."; }
}
/* ---------- "Alerts on this phone" (Web Push, 26 Oct 2026): per-device switches, stored with this browser's subscription ---------- */
function b64ToU8(s) {
  const p = "=".repeat((4 - (s.length % 4)) % 4), raw = atob((s + p).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
}
async function initPush() {
  const live = A$("pushLive"), rep = A$("pushReplay"), test = A$("testPush");
  if (!live || !live.isConnected) return;
  if (A$("installHint")) A$("installHint").onclick = () => showInstallHelp();
  const off = (why, kind) => { live.disabled = rep.disabled = test.disabled = true; say("pushMsg", why, kind || ""); };
  const supported = "serviceWorker" in navigator && "PushManager" in window && "Notification" in window && window.isSecureContext;
  if (!supported) {
    return off(isIos() && !isStandalone() ? "On iPhone, notifications work only in the installed app: install it (Share > Add to Home Screen), open it from "
      + "the home screen and come back here." : "This browser cannot receive push notifications here (it needs https or localhost, and a browser with Web Push).");
  }
  let key;
  try { key = await send("GET", "/api/push/key"); } catch (e) { return off("Could not reach the server."); }
  if (!key.configured) return off("Push notifications are not set up on the server yet (VAPID keys missing in .env: run python backend\\make_vapid_keys.py).");
  const reg = await navigator.serviceWorker.ready;
  let sub = await reg.pushManager.getSubscription();
  if (sub) {
    try {
      const st = await send("POST", "/api/me/push/status", { endpoint: sub.endpoint });
      live.checked = st.live; rep.checked = st.replay;
      if (st.last && !st.last.ok) say("pushMsg", "Last notification to this device failed (" + st.last.status + ").", "err");
    } catch (e) { /* shown as off */ }
  }
  const apply = async () => {
    try {
      if (!live.checked && !rep.checked) {
        if (sub) { await send("POST", "/api/me/push/unsubscribe", { endpoint: sub.endpoint }); await sub.unsubscribe(); sub = null; }
        return say("pushMsg", "Alerts on this phone are off.");
      }
      if (Notification.permission !== "granted") {
        const p = await Notification.requestPermission();
        if (p !== "granted") {
          live.checked = rep.checked = false;
          return say("pushMsg", "Notifications are blocked for this site. Allow them in the browser's site settings (lock icon > Permissions), then try again.", "err");
        }
      }
      if (!sub) sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64ToU8(key.key) });
      const j = sub.toJSON();
      await send("POST", "/api/me/push/subscribe", { subscription: { endpoint: j.endpoint, keys: j.keys }, live: live.checked, replay: rep.checked });
      say("pushMsg", "Saved for this device: " + [live.checked && "live alerts", rep.checked && "replay-demo alerts"].filter(Boolean).join(" and ") + ".", "ok");
    } catch (e) { say("pushMsg", "Could not turn on notifications: " + e.message, "err"); }
  };
  live.onchange = apply; rep.onchange = apply;
  test.onclick = async () => {
    if (!sub) return say("pushMsg", "Turn on one of the two switches first.", "err");
    test.disabled = true;
    try { const r = await send("POST", "/api/me/push/test", { endpoint: sub.endpoint }); say("pushMsg", r.reason, r.sent ? "ok" : "err"); }
    catch (e) { say("pushMsg", e.message, "err"); }
    test.disabled = false;
  };
}

async function pageProfile() {
  OPT = await send("GET", "/api/account/options");
  const me = await getAccount();                     // always 200 (no 401 in the console); null = not logged in
  if (!me) { location.href = "/login.html?next=/profile.html"; return; }
  const stations = await send("GET", "/api/stations");
  const ss = A$("station");
  stations.forEach((s) => { const o = document.createElement("option"); o.value = s.id; o.textContent = s.name; ss.appendChild(o); });
  const box = A$("conds");
  OPT.conditions.forEach((c) => {
    const l = document.createElement("label"); l.className = "check";
    l.innerHTML = "<input type='checkbox' name='cond' value='" + c + "'> " + GROUP_LABEL[c];
    box.appendChild(l);
  });
  fillProfile(me);
  renderAcctNav(me);
  loadWeekly(A$("weeklyCard"), { station: me.station, mode: "live", groups: (me.groups || []).join(",") },
             (stations.find((s) => s.id === me.station) || {}).name + " (your home station, live data)");
  const q = new URLSearchParams(location.search);
  if (q.get("welcome") === "1") {
    say("topMsg", "Account created. Please add your age, home station and health conditions, then press \u201cSave profile\u201d.", "ok");
    if (me.email_configured) { A$("confirmReminder").hidden = false; }
  }
  if (q.get("verified") === "1") say("topMsg", "Thank you: your e-mail address is confirmed.", "ok");
  if (q.get("verified") === "0") say("topMsg", "That confirmation link is invalid, already used or expired. Use “Send confirmation e-mail” to get a new one.", "err");
  A$("age").oninput = renderDerived;
  box.onchange = renderDerived;

  const f = A$("profileForm");
  f.onsubmit = async (e) => {
    e.preventDefault();
    const g = formGroups();
    if (A$("age").value.trim() !== "" && !(Number.isInteger(g.age) && g.age >= 0 && g.age <= 120)) { say("saveMsg", "Age must be a whole number from 0 to 120.", "err"); return; }
    const wn = waNorm(A$("waNumber").value);
    if (wn && !E164_RE.test(wn)) { say("saveMsg", "WhatsApp number must be in international format with the country code, e.g. +919876543210.", "err"); A$("waNumber").focus(); return; }
    if ((A$("waAlerts").checked || A$("waReplay").checked) && !wn) { say("saveMsg", "Add your WhatsApp number to receive alerts by WhatsApp.", "err"); A$("waNumber").focus(); return; }
    busy(f, true); say("saveMsg", "Saving...");
    try {
      const r = await send("PUT", "/api/me", { name: A$("pName").value, age: g.age, station: A$("station").value, conditions: g.conds,
        alert_from: A$("alertFrom").value === "" ? null : +A$("alertFrom").value, email_alerts: A$("emailAlerts").checked, replay_emails: A$("replayEmails").checked,
        whatsapp: waNorm(A$("waNumber").value), whatsapp_alerts: A$("waAlerts").checked, replay_whatsapp: A$("waReplay").checked });
      fillProfile(r);
      say("saveMsg", "Profile saved. Opening the replay demo\u2026", "ok");
      setTimeout(() => { location.href = "/"; }, 1000);          // after saving, go to the replay page (~1 s)
      return;                                                     // the form stays disabled until the page changes
    } catch (err) { say("saveMsg", err.message, "err"); }
    busy(f, false);
  };
  A$("testWa").onclick = async () => {        // sends to the number in the field (saved or not); the delivery result arrives a few seconds later
    const wn = waNorm(A$("waNumber").value);
    if (!E164_RE.test(wn)) { say("waMsg", "Enter your WhatsApp number in international format first, e.g. +919876543210.", "err"); return; }
    A$("testWa").disabled = true; say("waMsg", "Sending\u2026");
    try {
      const r = await send("POST", "/api/me/test-whatsapp", { whatsapp: wn });
      say("waMsg", r.sent ? r.reason : "Not sent: " + (r.code ? r.code + ": " : "") + r.reason, r.sent ? "ok" : "err");
      const refresh = async () => { const me = await getAccount(); if (me) renderWaLast(me); };
      refresh();
      if (r.sent) { setTimeout(refresh, ((r.check_after_s || 8) + 3) * 1000); setTimeout(refresh, ((r.check_after_s || 8) + 12) * 1000); }
    } catch (err) { say("waMsg", err.message, "err"); }
    A$("testWa").disabled = false;
  };
  A$("sendVerify").onclick = async () => {
    try { const r = await send("POST", "/api/me/send-verification"); say("verifyMsg", r.sent ? "Sent. Please check your inbox (and spam folder)." : r.reason, r.sent ? "ok" : "err"); }
    catch (err) { say("verifyMsg", err.message, "err"); }
  };
  // Log out: the button in the top bar (ui.js renderAcctNav)
  const df = A$("deleteForm");
  df.onsubmit = async (e) => {
    e.preventDefault();
    if (!confirm("Delete your account and all its data from this computer? This cannot be undone.")) return;
    busy(df, true);
    try { await send("POST", "/api/me/delete", { password: A$("delPassword").value }); location.href = "/login.html?deleted=1"; }
    catch (err) { say("delMsg", err.message, "err"); busy(df, false); }
  };
  initPush();
}

const PAGES = { signup: pageSignup, login: pageLogin, forgot: pageForgot, reset: pageReset, profile: pageProfile };
initServerBar(() => location.reload());
bindShowPassword();
(PAGES[document.body.dataset.page] || (() => Promise.resolve()))().catch((e) => {
  console.error(e);
  const m = document.getElementById("msg") || document.getElementById("topMsg");
  if (m) say(m.id, "Could not load: " + e.message, "err");
});
if (new URLSearchParams(location.search).get("deleted") === "1" && document.getElementById("msg")) say("msg", "Your account and all its data were deleted.", "ok");
