/* Shared presentation helpers for the replay page (app.js) and the live page (live.js). No forecast, alert or advice logic lives here. */
"use strict";
const $ = (id) => document.getElementById(id);
/* Guarded lookup for the account code: a missing element is reported in the console (it means the page and the script do not match, e.g. an old
   cached file) and a detached placeholder is returned, so one missing element cannot stop the rest of the page from loading. */
function el(id) {
  const e = document.getElementById(id);
  if (e) return e;
  console.error("page element #" + id + " is missing (page and script do not match; press Ctrl+F5 to reload)");
  return document.createElement("div");
}
const CAT_CLASS = (c) => "cat-" + String(c || "").replace(/\s+/g, "");          // pill background colour
const CC = (c) => "cc-" + String(c || "").replace(/\s+/g, "");                  // accent colour variable (--cc)
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const CONF_SHORT = { high: "High confidence", medium: "Moderate confidence", low: "Tendency only" };

function bannerShort(s) {                                 // "2026-04-24 02:00" -> "24 Apr, 02:00" (short banner time on phones)
  const m = /^(\d{4})-(\d\d)-(\d\d) (\d\d:\d\d)/.exec(s || "");
  return m ? (+m[3]) + " " + MONTHS[+m[2] - 1] + ", " + m[4] : (s || "");
}
function shortTime(s) {                                   // "2026-04-17 15:00" -> "17 Apr 15:00"
  const m = /^(\d{4})-(\d\d)-(\d\d) (\d\d:\d\d)/.exec(s || "");
  return m ? (+m[3]) + " " + MONTHS[+m[2] - 1] + " " + m[4] : (s || "");
}

/* Display names: never show the raw keys ("pm25") to users */
const POLL_NAME = { pm25: "PM2.5", pm10: "PM10", no2: "NO\u2082", so2: "SO\u2082", o3: "O\u2083", co: "CO" };
const pn = (key) => POLL_NAME[String(key || "").toLowerCase()] || String(key || "");

/* Pollutants tab. Each bar is the CPCB sub-index (0-500 scale with the CPCB category bands) of the 24 h / 8 h AVERAGE concentration it is computed
   from; the current hourly value is shown on a second line for reference. */
function renderPollutants(pollutants, main) {
  const box = $("pollBars");
  box.innerHTML = "";
  if (!pollutants) { box.textContent = "No pollutant data for this hour."; return; }
  pollutants.forEach((p) => {
    const row = document.createElement("div");
    row.className = "bar-row " + CC(p.category);
    const pct = p.si == null ? 0 : Math.min(p.si, 500) / 5;
    const avgTxt = p.avg == null ? "not available (too few valid hours)" : "<b>" + p.avg + "</b> " + p.unit;
    const siTxt = p.si == null ? "sub-index n/a" : "sub-index <b>" + p.si + "</b> (" + p.category + ")";
    row.innerHTML = "<div class='bar-label'>" + p.label + (p.key === main ? "<span class='mainmark'>main</span>" : "") + "</div>" +
      "<div class='bar-track' role='img' aria-label='" + p.label + " sub-index " + (p.si == null ? "not available" : p.si + ", " + p.category) + "'><div class='bar-fill' style='width:" + pct + "%'></div></div>" +
      "<div class='bar-meta'>" + p.window + " average: " + avgTxt + " \u00b7 " + siTxt + "</div>" +
      "<div class='bar-meta sub'>now (hourly): " + (p.value == null ? "no reading" : p.value + " " + p.unit) + "</div>";
    box.appendChild(row);
  });
  const scale = document.createElement("div");
  scale.className = "bar-row scale";
  scale.innerHTML = "<div></div><div class='bar-ruler' aria-hidden='true'>" + [0, 50, 100, 200, 300, 400, 500].map((v) => "<span style='" + (v === 500 ? "right:0" : "left:" + v / 5 + "%") + "'>" + v + "</span>").join("") + "</div>";
  box.appendChild(scale);
}


/* ---------- optional account (login). Guests keep the browser-only profile. ---------- */
const GROUP_LABEL = { lung: "Lung disease (asthma/COPD)", heart: "Heart disease", pregnant: "Pregnant", outdoor_worker: "Outdoor worker",
                      athlete: "Regular outdoor exerciser", child: "Child (under 14)", older: "Older adult (60 or over)" };
async function getAccount() {                    // the logged-in user's own profile, or null for a guest (or if the server cannot be reached)
  try { const r = await apiFetch("/api/auth/session", { credentials: "same-origin", cache: "no-store" }); return r.ok ? (await r.json()).user : null; } catch (e) { return null; }
}

/* CPCB scale bar (0-500) under the current AQI: coloured category bands and a marker at the value. The category name is always shown in the pill
   next to the number, so colour is never the only cue. */
function renderScale(el, aqi) {
  if (!el) return;
  if (aqi == null || isNaN(aqi)) { el.innerHTML = ""; el.removeAttribute("role"); return; }
  const v = Math.max(0, Math.min(500, Number(aqi)));
  el.setAttribute("role", "img");
  el.setAttribute("aria-label", "AQI " + aqi + " on the CPCB scale from 0 to 500");
  el.innerHTML = "<div class='scale-track'>" + ["good", "sat", "mod", "poor", "vpoor", "sev"].map((c) => "<span style='background:var(--c-" + c + ")'></span>").join("") +
    "<i class='scale-marker' style='left:" + (v / 5) + "%'></i></div><div class='scale-labels' aria-hidden='true'>" +
    [0, 50, 100, 200, 300, 400, 500].map((x) => "<span style='" + (x === 500 ? "right:0" : "left:" + x / 5 + "%") + "'>" + x + "</span>").join("") + "</div>";
}

/* footer on the account pages: the full disclaimer and the numbered sources (the replay and live pages fill them themselves) */
async function initFooter() {
  if (!document.querySelector("footer[data-autofoot]") || location.protocol === "file:") return;
  try {
    const r = await fetch("/api/meta"); if (!r.ok) return;
    const m = await r.json();
    const d = document.getElementById("disclaimer"); if (d && !d.textContent) d.textContent = m.disclaimer;
    const ol = document.getElementById("refs");
    if (ol && !ol.children.length) Object.entries(m.references).forEach(([k, v]) => { const li = document.createElement("li"); li.value = +k; li.textContent = v; ol.appendChild(li); });
  } catch (e) { /* the footer keeps its short disclaimer */ }
}
initFooter();

/* charts use the site font and the muted text colour */
if (window.Chart && Chart.defaults) {
  Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
  Chart.defaults.color = getComputedStyle(document.documentElement).getPropertyValue("--muted").trim() || "#566476";
}

/* sticky-banner self-test helper: the banner must sit directly under the top bar when the top bar is sticky (tablet and wider), else at the top */
function stickyTarget() {
  const head = document.querySelector(".topbar");
  return head && getComputedStyle(head).position === "sticky" ? head.getBoundingClientRect().bottom : 0;
}
/* Header account line on every page: "Signed in as <name> · Profile · Log out", or "Guest · Log in / Create account" */
function renderAcctNav(me) {
  const el = document.getElementById("acctNav");
  if (!el) return;
  el.innerHTML = "";
  const link = (text, href) => { const a = document.createElement("a"); a.href = href; a.textContent = text; return a; };
  const btnLink = (text, href) => { const a = link(text, href); a.className = "btn-sm"; return a; };
  if (me) {
    const who = document.createElement("span"); who.className = "who"; who.append("Signed in as ");
    const b = document.createElement("b"); b.textContent = me.name; who.appendChild(b);
    const out = document.createElement("button"); out.type = "button"; out.className = "btn-sm secondary"; out.id = "navLogout"; out.textContent = "Log out";
    out.onclick = async () => {
      try { await fetch("/api/auth/logout", { method: "POST", credentials: "same-origin" }); } catch (e) { /* ignore */ }
      location.href = "/login.html";
    };
    el.append(who);
    if (location.pathname !== "/profile.html") el.append(btnLink("Profile", "/profile.html"));
    el.append(out);
  } else {
    const who = document.createElement("span"); who.className = "who"; who.textContent = "Guest (no account)";
    el.append(who, btnLink("Log in / Create account", "/login.html"));
  }
  if (typeof placeInstall === "function") placeInstall();          // keep the "Install app" button (PWA) in the re-rendered area
}
function accountSummary(me) {                    // one line for the settings drawers; the name is filled in with textContent by the caller
  const g = me.groups.length ? me.groups.map((x) => GROUP_LABEL[x] || x).join(", ") : "healthy adult";
  return "Signed in as <b></b>. Profile from your account: " + g + "; alert from AQI " + me.alert_effective + ". <a href='/profile.html'>Edit profile</a>";
}

/* ---------- personalised advice (server: advice.personal_advice). Every line keeps its [n] source; trend / best time say "(our forecast)". ----------
   Readability (26 Oct 2026, presentation only): the server sends each line's unchanged text plus "marked" = the same text with **...** around key phrases,
   shown here in bold; a summary (category badge, status line, the TOP 3 actions with icons) comes first and "Show all advice" expands the rest. */
const escHtml = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
function md(s) { return escHtml(s).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>"); }          // **...** -> <strong> (after escaping)
/* list-item class: the trend line's icon follows its direction (up, down, changing, steady); the best-time line has a clock */
function paClass(x) { return "pa-" + x.kind + (x.dir ? " dir-" + x.dir : ""); }
function personalLine(p) { return md(p.marked || p.text) + " <span class='src'>" + escHtml(p.source) + "</span>"; }
/* small "How is this calculated?" note for the best-time line (collapsed) */
function howHtml(pa) {
  return pa && pa.best_how ? "<details class='howcalc'><summary>ⓘ How is this calculated?</summary><p>" + escHtml(pa.best_how) + "</p></details>" : "";
}
function catBadge(cat) { return cat ? "<span class='catpill " + CAT_CLASS(cat) + "'>" + escHtml(cat) + "</span>" : ""; }
const LEVEL_TEXT = { alert: "Alert level reached for your profile", advisory: "Advisory for your profile", none: "No special precautions needed for your profile" };
/* the TOP 3 actions (server: advice.top_actions / weekly top3), each with a simple icon (CSS mask, class ic-<name>) and its source */
function topActionsHtml(items, pa, cls) {
  return "<ul class='top-acts " + (cls || "") + "'>" + items.map((x) => "<li class='top-act ic-" + escHtml(x.icon || "info") + (x.kind ? " " + paClass(x) : "") + "'>" +
    personalLine(x) + (x.kind === "best_time" ? howHtml(pa) : "") + "</li>").join("") + "</ul>";
}
/* summary: coloured category badge + one-line status + the top 3 actions */
function adviceSummaryHtml(a, pa, status) {
  if (!a || !pa) return "";
  return "<div class='adv-summary'><p class='adv-status'>" + catBadge(a.category) + " <span><b>AQI " + a.aqi + "</b> · " + escHtml(LEVEL_TEXT[a.level] || "") +
    (status ? " · <span class='muted'>" + status + "</span>" : "") + "</span></p>" +
    (a.level === "none" ? "" : "<p class='adv-h'>Your top 3 actions</p>") + topActionsHtml(pa.top3 || [], pa) + "</div>";
}
/* everything not in the summary, grouped: amber "may affect you" (the CPCB category statement, main pollutant), green "what you can do" */
function adviceRestHtml(a, pa, open) {
  if (!pa) return "";
  const shown = new Set((pa.top3 || []).flatMap((x) => [x.text, ...(x.covers || [])]));     // a merged group line covers the single ones
  const affect = [pa.headline, pa.pollutant].filter(Boolean);
  const todo = pa.full.filter((x) => !["headline", "pollutant"].includes(x.kind) && !shown.has(x.text));
  return "<details class='adv-more'" + (open ? " open" : "") + "><summary>Show all advice</summary>" +
    "<section class='asec sec-affect'><h4 class='sec-h'>May affect you</h4><ul class='personal'>" +
    affect.map((x) => "<li class='" + paClass(x) + "'>" + personalLine(x) + "</li>").join("") + "</ul></section>" +
    (todo.length ? "<section class='asec sec-do'><h4 class='sec-h'>What you can do</h4><ul class='personal'>" +
      todo.map((x) => "<li class='" + paClass(x) + (x.kind === "caution" ? " caution" : "") + "'>" + personalLine(x) + (x.kind === "best_time" ? howHtml(pa) : "") + "</li>").join("") +
      "</ul></section>" : "") + "</details>";
}
function personalHtml(pa) {                       // full version (kept for callers that want everything expanded)
  if (!pa) return "";
  return adviceRestHtml({ category: pa.category, aqi: pa.aqi, level: pa.level }, { ...pa, top3: [] }, true);
}

/* ---------- donut (SVG on the website only; e-mails use none). segments: [{value, cls, label, hatch}] ---------- */
let DONUT_N = 0;
function donutSvg(segs, center, size, aria) {
  const id = "dn" + (++DONUT_N), R = 40, C = 2 * Math.PI * R, total = segs.reduce((s, x) => s + x.value, 0) || 1, gap = segs.filter((x) => x.value).length > 1 ? 1.2 : 0;
  let off = 0, arcs = "";
  segs.forEach((x, i) => {
    if (!x.value) return;
    const len = Math.max(x.value / total * C - gap, 0.5);
    arcs += "<circle class='dn-seg " + (x.cls || "") + "' data-i='" + i + "' cx='50' cy='50' r='" + R + "' fill='none' stroke-width='16'" +
      (x.hatch ? " stroke='url(#" + id + "h)'" : "") + " stroke-dasharray='" + len.toFixed(2) + " " + (C - len).toFixed(2) + "' stroke-dashoffset='" + (-off).toFixed(2) +
      "' transform='rotate(-90 50 50)'><title>" + escHtml(x.label) + "</title></circle>";
    off += x.value / total * C;
  });
  return "<svg class='donut' viewBox='0 0 100 100' width='" + size + "' height='" + size + "' role='img' aria-label='" + escHtml(aria) + "'>" +
    "<defs><pattern id='" + id + "h' width='4' height='4' patternUnits='userSpaceOnUse' patternTransform='rotate(45)'><rect width='4' height='4' fill='#e5e9ef'/>" +
    "<rect width='1.6' height='4' fill='#9aa5b1'/></pattern></defs><circle cx='50' cy='50' r='" + R + "' fill='none' stroke='var(--line)' stroke-width='16'/>" + arcs +
    "<text x='50' y='48' text-anchor='middle' class='dn-big'>" + escHtml(center[0]) + "</text><text x='50' y='61' text-anchor='middle' class='dn-small'>" +
    escHtml(center[1] || "") + "</text>" + (center[2] ? "<text x='50' y='71' text-anchor='middle' class='dn-small'>" + escHtml(center[2]) + "</text>" : "") + "</svg>";
}
const CPCB_CATS = ["Good", "Satisfactory", "Moderate", "Poor", "Very Poor", "Severe"];
const STROKE = (c) => "st-" + String(c || "").replace(/\s+/g, "");

/* ---------- "This week's air and your health" (server: backend/weekly.py; health text only from weekly_advice_rules.json) ---------- */
const WK_SHORT = { Good: "Good", Satisfactory: "Satisf.", Moderate: "Moderate", Poor: "Poor", "Very Poor": "V. Poor", Severe: "Severe" };
const WK_TINY = { Good: "Good", Satisfactory: "Sat.", Moderate: "Mod.", Poor: "Poor", "Very Poor": "V.Poor", Severe: "Sev." };   // phones (full name in the aria-label)
const WK_TREND = { rising: ["↗", "rising"], falling: ["↘", "falling"], steady: ["→", "steady"], unknown: ["–", "not enough data"] };
function wkRange(a, b) {                     // "7–13 Oct" (same month) or "28 Sep – 4 Oct"
  const x = wkDate(a).split(" "), y = wkDate(b).split(" ");
  return x[1] === y[1] ? x[0] + "–" + y[0] + " " + y[1] : wkDate(a) + " – " + wkDate(b);
}
function wkNote(text, id, used) {            // source note: the text's own trailing "[n]." is replaced by ONE linked citation
  return escHtml(String(text).replace(/\s*\[\d+\]\.?\s*$/, "")) + wkCite([id], used) + ".";
}
function wkCite(ids, used) { ids.forEach((i) => used.add(i)); return " <span class='src'>" + ids.map((i) => "<a href='#wk-ref-" + i + "'>[" + i + "]</a>").join("") + "</span>"; }
function wkList(items, used, cls) {
  return "<ul class='wk-list" + (cls ? " " + cls : "") + "'>" + items.map((x) => "<li" + (x.icon ? " class='top-act ic-" + escHtml(x.icon) + "'" : "") + ">" +
    md(x.marked || x.text) + wkCite(x.sources, used) + "</li>").join("") + "</ul>";
}
function wkDate(s) { const m = /^(\d{4})-(\d\d)-(\d\d)/.exec(s || ""); return m ? (+m[3]) + " " + MONTHS[+m[2] - 1] : s; }
/* donut "days per CPCB category" (official CPCB colours; 'no data' days grey hatched) */
function wkDonut(w) {
  const cnt = {}; let nodata = 0;
  w.days.forEach((d) => { if (d.aqi == null) nodata++; else cnt[d.category] = (cnt[d.category] || 0) + 1; });
  const segs = CPCB_CATS.map((c) => ({ value: cnt[c] || 0, cls: STROKE(c), label: c + ": " + (cnt[c] || 0) + " day" + (cnt[c] === 1 ? "" : "s"), cat: c }))
    .concat([{ value: nodata, hatch: true, label: "No data: " + nodata + " day" + (nodata === 1 ? "" : "s"), cat: "No data" }]);
  const bad = w.days_moderate_or_worse || 0;
  const legend = "<ul class='dn-legend'>" + segs.filter((x) => x.value).map((x) => "<li><span class='sw " + (x.hatch ? "sw-hatch" : CAT_CLASS(x.cat)) + "' aria-hidden='true'></span>" +
    escHtml(x.cat) + " <b>" + x.value + "</b></li>").join("") + "</ul>";
  return "<div class='wk-donut' data-counts='" + escHtml(JSON.stringify(Object.assign({}, cnt, nodata ? { "No data": nodata } : {}))) + "'>" +
    donutSvg(segs, [bad + " of 7", "days Moderate", "or worse"], 150, "Days per CPCB category: " + segs.filter((x) => x.value).map((x) => x.label).join(", ")) + legend + "</div>";
}
/* thin strip of 7 coloured dots, oldest -> newest, with day labels (keeps the day order / trend visible) */
function wkDots(days) {
  return "<div class='wk-dots' role='img' aria-label='Daily AQI, oldest to newest: " + days.map((d) => d.weekday + " " + d.label + " " + (d.aqi == null ? "no data" : d.aqi + " " + d.category)).join(", ") + "'>" +
    days.map((d) => "<div class='wk-day'><div class='wk-num'>" + (d.aqi == null ? "–" : d.aqi) + "</div><span class='wk-dot " + (d.aqi == null ? "wk-nodata" : CAT_CLASS(d.category)) +
      "' aria-hidden='true'></span><div class='wk-cat'>" + (d.aqi == null ? "no data" : "<span class='wk-long'>" + WK_SHORT[d.category] + "</span><span class='wk-tiny' aria-hidden='true'>" +
      WK_TINY[d.category] + "</span>") + "</div><div class='wk-lab'>" + d.weekday + "<br>" + d.label + "</div></div>").join("") + "</div>";
}
function renderWeekly(box, w, where) {
  if (!box) return;
  if (!w) { box.innerHTML = "<p class='small muted'>No data for a weekly summary at this station.</p>"; box.dataset.clock = ""; return; }
  box.dataset.clock = w.window.clock;                       // which replay / live clock this card describes
  const used = new Set();
  const past = !!(w.data && w.data.stale);    // live data older than 24 h: the LAST AVAILABLE week, never "this week" (replay is relative to its clock)
  let h = "<div class='wk-head'><h2 class='card-title'>" + (past ? "Last available week (" + wkRange(w.window.first, w.window.last) + ")" : "This week's air and your health") +
    "</h2><p class='small muted'>" + escHtml(where || "") + (where ? " · " : "") + wkDate(w.window.first) + " – " + wkDate(w.window.last) +
    (past ? " (the 7 full days before the newest data, hour ending " : " (the 7 full days before the replay time, ") + escHtml(w.window.clock_end || w.window.clock.slice(0, 16)) +
    " IST)</p>" +
    (past ? "<p class='wk-stale' role='status'>Data feed stopped: newest data is " + Math.round(w.data.age_hours) + " h old; this is not the current week.</p>" : "") + "</div>";
  const H = w.health;
  // summary first: worst-day badge + status line, the donut, the day strip
  if (w.enough) h += "<p class='adv-status'>" + (w.worst_category ? catBadge(w.worst_category) + " " : "") + "<span>Worst day: <b>" + escHtml(w.worst_category || "-") + "</b> · <b>" +
    w.days_moderate_or_worse + " of " + w.valid_days + "</b> days with data Moderate or worse</span></p>";
  h += "<div class='wk-visual'>" + wkDonut(w) + wkDots(w.days) + "</div>";
  if (!w.enough) {
    box.innerHTML = h + "<p class='wk-msg'>Not enough data for a weekly summary: only " + w.valid_days + " of 7 days have enough measurements (at least 5 are needed).</p>";
    return;
  }
  const tr = WK_TREND[w.trend.direction] || WK_TREND.unknown;
  h += "<div class='wk-chips'><span class='wk-chip'><span aria-hidden='true'>" + tr[0] + "</span> " + (past ? "That week" : "Last 7 days") + ": <b>" + tr[1] + "</b>" +
    (w.trend.last3 != null ? " (last 3 days " + w.trend.last3 + " vs " + w.trend.prev4 + " before)" : "") + "</span>" +
    "<span class='wk-chip'>Main pollutant: <b>" + escHtml(pn(w.dominant)) + "</b></span></div>" +
    "<p class='small muted wk-chipnote'>Main pollutant = the pollutant with the highest CPCB sub-index on most days; the WHO column compares against stricter " +
    "guideline levels.</p>";
  // top 3 actions (the profile's own first), then everything else behind "Show all advice"
  const top = (w.top3 || []).map((id) => H.actions.find((x) => x.id === id)).filter(Boolean);
  if (H.clean.length) h += "<section class='asec sec-do'><h3>" + (past ? "That week" : "This week") + "</h3>" + wkList(H.clean, used) + "</section>";
  if (top.length) h += "<p class='adv-h'>Your top 3 actions</p>" + wkList(top, used, "top-acts");
  const more = (H.short_term.length ? "<section class='asec sec-affect'><h3>" + (past ? "During that week, air like this may affect you" : "This week may affect you") + "</h3>" +
      wkList(H.short_term, used) + "</section>" : "") +
    (H.long_term.length ? "<section class='asec sec-continue'><h3>" + (past ? "If air like that week's continues" : "If this continues") + "</h3><p class='small muted'>Pollution was Moderate or worse on " +
      w.days_moderate_or_worse + (past ? " of those 7 days" : " of the last 7 days") + ". Long-term effects relate to exposure over months and years:</p>" + wkList(H.long_term, used) + "</section>" : "") +
    (H.actions.length ? "<section class='asec sec-do'><h3>What you can do</h3>" + wkList(H.actions, used) + "</section>" : "");
  if (more) h += "<details class='adv-more'><summary>Show all advice</summary>" + more + "</details>";
  h += "<details class='wk-poll'><summary>Show pollutant details</summary><div class='tablewrap'><table class='wk-table'><thead><tr><th>Pollutant</th><th>Days above India limit</th>" +
    "<th>Days above WHO guideline</th></tr></thead><tbody>" +
    w.exceedances.map((e) => "<tr><td>" + escHtml(e.name) + "</td><td>" + (e.days_with_data ? "<b>" + e.days_above_india + "</b> of " + e.days_with_data : "no data") +
      " <span class='muted small'>(" + e.india_limit + " " + escHtml(e.unit) + ", " + e.india_avg + ")</span>" + wkCite(["9"], used) + "</td><td>" +
      (e.days_with_data_who ? "<b>" + e.days_above_who + "</b> of " + e.days_with_data_who : "no data") + " <span class='muted small'>(" + e.who_level + " " +
      escHtml(e.unit) + ", " + e.who_avg + ")</span>" + wkCite(["8"], used) + "</td></tr>").join("") + "</tbody></table></div>" +
    "<p class='small muted wk-notes'>" + wkNote(w.notes.india, "9", used) + " " + wkNote(w.notes.who, "8", used) + "</p></details>";
  h += "<p class='small disclaimer'>" + escHtml(w.disclaimer) + " In an emergency call 112.</p>";
  h += "<details class='small wk-sources asec sec-src'><summary>Sources</summary><ol>" + Object.entries(w.references).filter(([k]) => used.has(k)).map(([k, r]) =>
    "<li value='" + k + "' id='wk-ref-" + k + "'>" + escHtml(r.text) + (r.url ? " <a href='" + escHtml(r.url) + "' rel='noopener' target='_blank'>" + escHtml(r.url.replace(/^https?:\/\//, "").slice(0, 60)) + "</a>" : "") + "</li>").join("") + "</ol></details>";
  box.innerHTML = h;
}
async function loadWeekly(box, params, where) {               // fetches /api/weekly and renders; ignores answers that arrive out of order
  const my = (box._wk = (box._wk || 0) + 1);
  try {
    const r = await apiFetch("/api/weekly?" + new URLSearchParams(params).toString(), { cache: "no-store" });
    const w = r.ok ? await r.json() : null;
    if (my === box._wk) renderWeekly(box, w, where);
  } catch (e) { /* the server bar reports connection problems */ }
}

/* ---------- "Server not running" bar (both pages) ----------
   Shown (red, top of the page) when a request to the backend fails or the page was opened as a file instead of through the server. It checks the server every
   3 s while shown and hides itself (and reloads the data) when the server answers again. */
const SERVER_START_CMD = "python -m uvicorn backend.app:app --port 8000";
let serverDownState = false, serverPoll = null, serverBackCb = null;
function serverBar() {
  let el = document.getElementById("serverDown");
  if (!el) {
    el = document.createElement("div"); el.id = "serverDown"; el.setAttribute("role", "alert"); el.hidden = true;
    const b = document.createElement("b"); b.textContent = "Server not running. ";
    const t = document.createElement("span"); t.id = "serverDownText";
    el.append(b, t);
    document.body.insertBefore(el, document.body.firstChild);
  }
  return el;
}
function setServerDown(down, why) {
  const el = serverBar();
  el.hidden = !down;
  document.getElementById("serverDownText").textContent = down
    ? (location.protocol === "file:" ? "This page was opened as a file. Start the server, then open http://127.0.0.1:8000 in the browser. " : "The page cannot reach the backend. ")
      + (navigator.onLine === false ? "This device is offline. " : "")
      + (["localhost", "127.0.0.1", "[::1]", ""].includes(location.hostname)
         ? "In a terminal in the project folder run: " + SERVER_START_CMD
         : "The server on the laptop cannot be reached: the laptop, the server and the tunnel must be running.") + (why ? "  (" + why + ")" : "") : "";
  const was = serverDownState; serverDownState = down;
  if (down && !serverPoll) serverPoll = setInterval(async () => {
    try { const r = await fetch("/api/meta", { cache: "no-store" }); if (r.ok && !r.headers.get("X-AQI-Offline")) setServerDown(false); } catch (e) { /* still down */ }
  }, 3000);
  if (!down && serverPoll) { clearInterval(serverPoll); serverPoll = null; }
  if (was && !down && serverBackCb) serverBackCb();
}
async function apiFetch(path, opts) {           // fetch + server-bar bookkeeping; throws like fetch
  let r;
  try { r = await fetch(path, opts); } catch (e) { setServerDown(true, e && e.message); throw e; }
  if (r.headers.get("X-AQI-Offline")) { setOffline(r.headers.get("X-AQI-Saved-At")); return r; }       // the amber offline banner says it all
  setOffline(false);
  if (serverDownState) setServerDown(false);
  return r;
}
function initServerBar(onBack) {
  serverBackCb = onBack || null;
  serverBar();
  if (location.protocol === "file:") setServerDown(true);
}

/* ---------- PWA (26 Oct 2026): service worker, offline banner, "Install app" ----------
   The service worker (sw.js) answers /api requests network-first; when the server cannot be reached it returns the last saved answer with the
   header X-AQI-Offline and its X-AQI-Saved-At time. The page then shows "Offline - showing data from <time>": a saved copy is never shown as current. */
let offlineSince = null, offlinePoll = null;
function offlineBar() {
  let el = document.getElementById("offlineBar");
  if (!el) {
    el = document.createElement("div"); el.id = "offlineBar"; el.setAttribute("role", "status"); el.hidden = true;
    document.body.insertBefore(el, document.body.firstChild);
  }
  return el;
}
function fmtLocal(iso) {
  const d = new Date(iso);
  if (isNaN(d)) return iso || "an earlier visit";
  return d.getDate() + " " + MONTHS[d.getMonth()] + " " + d.getFullYear() + ", " + String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0");
}
function setOffline(savedAt) {
  const el = offlineBar();
  if (savedAt === false) {                                   // a fresh answer arrived: back online
    if (!el.hidden) { el.hidden = true; offlineSince = null; document.documentElement.classList.remove("is-offline"); }
    if (offlinePoll) { clearInterval(offlinePoll); offlinePoll = null; }
    return;
  }
  if (!offlineSince || (savedAt && savedAt < offlineSince)) offlineSince = savedAt || offlineSince;     // the OLDEST copy on screen
  el.innerHTML = "<b>Offline - showing data from " + escHtml(fmtLocal(offlineSince)) + ".</b> This is a saved copy, NOT current air quality. " +
    "The page updates by itself when the server can be reached again.";
  el.hidden = false;
  document.documentElement.classList.add("is-offline");
  if (!offlinePoll) offlinePoll = setInterval(async () => {
    try {
      const r = await fetch("/api/meta", { cache: "no-store" });
      if (r.ok && !r.headers.get("X-AQI-Offline")) { setOffline(false); if (serverDownState) setServerDown(false); else if (serverBackCb) serverBackCb(); }
    } catch (e) { /* still offline */ }
  }, 5000);
}
function registerServiceWorker() {
  const secure = location.protocol === "https:" || ["localhost", "127.0.0.1", "[::1]"].includes(location.hostname);
  if (!("serviceWorker" in navigator) || !secure) return null;
  return navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => null);
}

/* "Install app": Android/Chrome uses the browser's install prompt; iPhone/iPad (Safari has no prompt) gets "Share > Add to Home Screen" steps */
let deferredInstall = null;
const isStandalone = () => (window.matchMedia && matchMedia("(display-mode: standalone)").matches) || navigator.standalone === true;
const isIos = () => /iphone|ipad|ipod/i.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
let INSTALL_BTN = null;
function installButton() {                        // the button lives at the start of the account area (#acctNav), which is re-rendered: placeInstall()
  if (!INSTALL_BTN) {
    const b = document.createElement("button"); b.type = "button"; b.id = "installBtn"; b.className = "install-btn"; b.hidden = true;
    b.innerHTML = "<span class='ib-ico' aria-hidden='true'></span>Install<span class='ib-long'>&nbsp;app</span>";   // drawn icon: no font glyph
    b.onclick = installNow;
    INSTALL_BTN = b;
  }
  placeInstall();
  return INSTALL_BTN;
}
function placeInstall() {
  const nav = document.getElementById("acctNav");
  if (nav && INSTALL_BTN && INSTALL_BTN.parentNode !== nav) nav.prepend(INSTALL_BTN);
}
function showInstallHelp() {
  let d = document.getElementById("installHelp");
  if (!d) {
    d = document.createElement("div"); d.id = "installHelp"; d.setAttribute("role", "dialog"); d.setAttribute("aria-modal", "true");
    d.setAttribute("aria-labelledby", "installHelpTitle");
    d.innerHTML = "<div class='ih-card'><h2 id='installHelpTitle'>Install AQ Health on this phone</h2>" +
      (isIos() ? "<ol><li>In <b>Safari</b>, tap the <b>Share</b> button (the square with an arrow pointing up).</li><li>Scroll and tap <b>Add to Home Screen</b>.</li>" +
        "<li>Tap <b>Add</b>. The app opens from its icon like any other app.</li></ol><p class='small muted'>Alerts on an iPhone work only in the installed app " +
        "(iOS 16.4 or newer): open it from the home screen, then turn on “Alerts on this phone” in your profile.</p>"
               : "<ol><li>Open the browser menu (<b>⋮</b>, top right in Chrome).</li><li>Tap <b>Install app</b> or <b>Add to Home screen</b>.</li>" +
        "<li>Tap <b>Install</b>. The app opens from its icon like any other app.</li></ol>") +
      "<p class='small muted'>The app shows the data of the server running on the laptop: the laptop and the server must stay on.</p>" +
      "<div class='ih-actions'><button type='button' id='installHelpClose'>OK</button></div></div>";
    document.body.appendChild(d);
    d.querySelector("#installHelpClose").onclick = () => { d.hidden = true; };
    d.addEventListener("keydown", (e) => { if (e.key === "Escape") d.hidden = true; });
  }
  d.hidden = false;
  d.querySelector("#installHelpClose").focus();
}
async function installNow() {
  if (deferredInstall && !isIos()) {                         // iPhone/iPad: always the Safari steps (iOS has no install prompt)
    deferredInstall.prompt();
    try { await deferredInstall.userChoice; } catch (e) { /* closed */ }
    deferredInstall = null;
    const b = installButton(); if (b) b.hidden = true;
  } else {
    showInstallHelp();
  }
}
function initPwa() {
  registerServiceWorker();
  if (isStandalone()) document.documentElement.classList.add("standalone");
  const b = installButton();
  if (b && isIos() && !isStandalone()) b.hidden = false;                 // iPhone: no prompt event, show the steps
  window.addEventListener("beforeinstallprompt", (e) => { e.preventDefault(); deferredInstall = e; const x = installButton(); if (x && !isStandalone()) x.hidden = false; });
  window.addEventListener("appinstalled", () => { deferredInstall = null; const x = installButton(); if (x) x.hidden = true; });
}
if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", initPwa); else initPwa();

/* Tabs (Forecast / Health advice / Pollutants) and the settings drawer */
function bindUi(onForecastTab) {
  const names = ["forecast", "advice", "pollutants"];
  const select = (name) => {
    names.forEach((t) => { const on = t === name; $("tabbtn-" + t).setAttribute("aria-selected", on ? "true" : "false"); $("tab-" + t).hidden = !on; });
    if (name === "forecast" && onForecastTab) onForecastTab();
  };
  names.forEach((t) => { $("tabbtn-" + t).onclick = () => select(t); });
  document.querySelector(".tablist").onkeydown = (e) => {
    const i = names.findIndex((t) => $("tabbtn-" + t).getAttribute("aria-selected") === "true");
    if (e.key === "ArrowRight" || e.key === "ArrowLeft") { const n = names[(i + (e.key === "ArrowRight" ? 1 : names.length - 1)) % names.length]; select(n); $("tabbtn-" + n).focus(); }
  };
  const openS = () => { $("settings").hidden = false; $("scrim").hidden = false; $("openSettings").setAttribute("aria-expanded", "true"); $("closeSettings").focus(); };
  const closeS = () => { $("settings").hidden = true; $("scrim").hidden = true; $("openSettings").setAttribute("aria-expanded", "false"); $("openSettings").focus(); };
  $("openSettings").onclick = openS; $("closeSettings").onclick = closeS; $("scrim").onclick = closeS;
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !$("settings").hidden) closeS(); });
  const q = new URLSearchParams(location.search);                 // developer shortcuts: ?tab=advice|pollutants  ?settings=1  ?details=1
  if (names.includes(q.get("tab"))) select(q.get("tab"));
  if (q.get("settings") === "1") openS();
  if (q.get("details") === "1" && $("details")) $("details").open = true;
}

/* x-axis labels: on a phone only some horizons are labelled (the gridline stays at every horizon) */
const NARROW = () => window.innerWidth < 560;
const LABEL_SM = [-48, -24, 0, 12, 24];

/* Disclaimer and numbered sources, shown in the footer and in the advice tab */
function fillDisclaimer(meta) {
  $("disclaimer").textContent = meta.disclaimer;
  $("disclaimer2").textContent = meta.disclaimer;
  Object.entries(meta.references).forEach(([k, v]) => {
    ["refs", "refs2"].forEach((id) => { const li = document.createElement("li"); li.value = +k; li.textContent = v; $(id).appendChild(li); });
  });
}

/* The main pages show only the research-grade horizons (+1, +6, +12, +24 h). The longer horizons (+36, +48, +72 h) have no consistent skill over
   persistence in our tests (+36 h mixed, +48/+72 h none), so they are listed only in a small "experimental" table under Details. */
const MAIN_MAX_H = 24;
function renderExperimental(forecasts, persistenceOf) {
  const tb = $("expTable").querySelector("tbody");
  tb.innerHTML = "";
  forecasts.filter((f) => f.horizon > MAIN_MAX_H).forEach((f) => {
    const tr = document.createElement("tr");
    tr.innerHTML = f.available === false
      ? "<td>+" + f.horizon + " h</td><td>" + f.target_end + "</td><td colspan='3' class='muted'>not available (data gap)</td>"
      : "<td>+" + f.horizon + " h</td><td>" + f.target_end + "</td><td><b>" + f.aqi + "</b> <span class='catpill " + CAT_CLASS(f.category) + "'>" + f.category + "</span></td>" +
        "<td>" + f.range_low + " to " + f.range_high + "</td><td>" + persistenceOf(f) + "</td>";
    tb.appendChild(tr);
  });
}
