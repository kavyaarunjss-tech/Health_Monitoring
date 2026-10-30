/* AQI forecast website - Live mode (minimal). Plain JavaScript. */
"use strict";
const rint = (x) => Math.floor(Number(x) + 0.5);
const TIER = { high: "High confidence", medium: "Moderate confidence", low: "Low confidence: tendency only" };
const DEFAULT_ALERT = { vulnerable: 101, healthy: 201 };
const VULN = ["lung", "heart", "child", "older", "pregnant", "outdoor_worker", "athlete"];
let chart = null;
let ACCOUNT = null;                 // logged-in user's own profile, or null (guest: the browser profile shared with the replay page)

function profile() {
  if (ACCOUNT) return { groups: ACCOUNT.groups, alert_from: ACCOUNT.alert_effective, station: ACCOUNT.station };
  try { const p = JSON.parse(localStorage.getItem("aqiProfile") || "null"); if (p) return p; } catch (e) { /* ignore */ }
  return { groups: [], alert_from: 201 };
}
function alertLevelFor(p) {
  const vuln = (p.groups || []).some((g) => VULN.includes(g));
  return Math.min(p.alert_from, vuln ? DEFAULT_ALERT.vulnerable : DEFAULT_ALERT.healthy, 301);
}
async function api(path, opts) {
  const r = await apiFetch(path, opts);
  if (!r.ok) throw new Error(path + " -> HTTP " + r.status);
  return r.json();
}
const catCell = (c) => "<span class='catpill " + CAT_CLASS(c) + "'>" + c + "</span>";
const fmtH = (h) => { const a = Math.abs(h); return a < 1 ? "now" : (h < 0 ? Math.round(a) + " h ago (already passed)" : "in " + Math.round(a) + " h"); };

async function init() {
  const meta = await api("/api/meta");
  fillDisclaimer(meta);
  ACCOUNT = await getAccount();
  renderAcctNav(ACCOUNT);
  if (ACCOUNT) {
    el("guestNote").hidden = true;
    const box = el("acctBox"); box.hidden = false; box.innerHTML = accountSummary(ACCOUNT); box.querySelector("b").textContent = ACCOUNT.name;
  }
  bindUi(() => { if (chart) chart.resize(); });
  const sts = await api("/api/live/stations");
  const sel = $("station");
  sts.forEach((s) => {
    const o = document.createElement("option");
    o.value = s.id; o.textContent = s.name + (s.age_hours != null ? " (" + Math.round(s.age_hours) + " h old)" : " (no data)");
    sel.appendChild(o);
  });
  let st = "silkboard";
  const p = profile();
  if (p.station && sts.some((s) => s.id === p.station)) st = p.station;
  const urlSt = new URLSearchParams(location.search).get("station");    // opened from a push notification: that station
  if (urlSt && sts.some((s) => s.id === urlSt)) st = urlSt;
  sel.value = st;
  sel.onchange = () => show();
  $("profileInfo").textContent = "Your alert level: AQI " + alertLevelFor(p) + ".";
  try {
    const sc = await api("/api/scheduler/status");
    const last = sc.last ? "last update " + sc.last.finished.replace("T", " ") + (sc.last.ok ? " (ok)" : " (FAILED, showing older data)") : "no update has run yet";
    const next = (sc.jobs.find((j) => j.id === "hourly") || {}).next_run;
    $("updateInfo").textContent = sc.enabled ? "Automatic updates: on, hourly at :10; " + last + (next ? "; next " + next.replace(" IST", "") : "") + "."
                                             : "Automatic updates: off (start the server with AQI_SCHEDULER=1). Data is only as new as the last manual update.";
  } catch (e) { $("updateInfo").textContent = ""; }
  await show();
  if (/[?&]selftest=live/.test(location.search)) await selfTestLive();
  else if (/[?&]selftest=sticky/.test(location.search)) await selfTestSticky();
}

async function show() {
  const st = await api("/api/live/state?station=" + $("station").value);
  const b = $("banner");
  b.className = "banner banner-" + st.severity;
  const sevText = { fresh: "Data is current", delayed: "Data is delayed", stale: "DATA IS OLD", none: "No data" }[st.severity];
  $("bannerText").textContent = st.severity === "none" ? "No valid observation for this station: no forecast."
    : sevText + ": the newest observation is " + Math.round(st.age_hours) + " hours old (hour ending " + st.last_obs_end + " IST). Current time " + st.now + " IST.";
  $("stationTitle").textContent = st.station_name;
  $("stationCard").className = "card now " + (st.forecasts.length ? CC(st.last_category) : "");
  $("warnings").innerHTML = "";
  st.warnings.forEach((w) => { const li = document.createElement("li"); li.textContent = w; $("warnings").appendChild(li); });
  if (!st.forecasts.length) {
    $("lastAqi").textContent = "n/a"; $("lastCat").textContent = "-"; renderScale($("nowScale"), null); $("fcTable").querySelector("tbody").innerHTML = ""; return;
  }
  $("lastTime").textContent = st.last_obs_end;
  $("lastAqi").textContent = st.last_aqi;
  renderScale($("nowScale"), st.last_aqi);
  const pill = $("lastCat"); pill.textContent = st.last_category; pill.className = "catpill " + CAT_CLASS(st.last_category);
  $("ageInfo").textContent = "Data age: " + Math.round(st.age_hours) + " h. Model trained through: " + (st.trained_through || "no model (persistence fallback)") + ".";
  $("nowExtra").textContent = st.dominant_now ? "Main pollutant: " + pn(st.dominant_now) : "";
  drawChart(st);
  fillTable(st);
  renderStrip(st);
  renderPollutants(st.pollutants, st.dominant_now);
  loadWeekly($("weeklyCard"), { station: st.station, mode: "live", groups: (profile().groups || []).join(",") }, st.station_name);
  if (typeof loadStations === "function")                     // "All stations now" (stations.js): newest values with their age; click = open that station
    loadStations($("stationsCard"), { mode: "live" }, st.station, (id) => { $("station").value = id; show(); window.scrollTo({ top: 0, behavior: "smooth" }); });
  await advice(st);
}

/* forecast cards: one per real horizon, counted from the last observation */
function alertLevelOf(f) {
  const t = alertLevelFor(profile());
  return f.aqi >= t ? "likely" : (f.range_high >= t ? "possible" : "none");
}
function renderStrip(st) {
  const box = $("strip"); box.innerHTML = "";
  const stale = st.age_hours > 12;
  const main = st.forecasts.filter((f) => f.horizon <= MAIN_MAX_H);
  if (main.length && main.every((f) => f.status === "past")) {           // data too old: do NOT fill the gap with the 36-72 h experimental horizons
    const m = document.createElement("div");
    m.className = "strip-msg"; m.setAttribute("role", "status");
    m.textContent = "No forecast for the coming hours: the newest data is " + Math.round(st.age_hours) + " h old, so every forecast horizon (up to 24 h) has already passed.";
    box.appendChild(m);
    return;
  }
  main.forEach((f) => {
    const d = document.createElement("div");
    d.setAttribute("role", "listitem");
    const past = f.status === "past", tend = f.horizon > 24, lv = alertLevelOf(f);
    d.className = "fc-card " + CC(f.category) + (tend ? " tendency" : "") + (past ? " past" : "");
    const rel = past ? "passed " + Math.round(Math.abs(f.hours_from_now)) + " h ago" : "in " + Math.round(f.hours_from_now) + " h";
    let badge = "";
    if (lv !== "none") {
      const notified = !stale && f.horizon <= (lv === "likely" ? 24 : 12) && !past;
      badge = "<div><span class='fc-badge " + (lv === "possible" ? "possible " : "") + (notified ? "" : "quiet") + "' title='Reaches your alert level" + (notified ? "" : "; no alert e-mail for this") + "'>&#9888; " +
        (lv === "likely" ? "Likely" : "Possible") + (notified ? "" : " (not notified)") + "</span></div>";
    }
    d.innerHTML = "<div class='fc-h'>+" + f.horizon + " h</div><div class='fc-t'>" + shortTime(f.target_end) + "</div><div class='fc-t'>" + rel + "</div>" +
      "<div class='fc-aqi'>" + f.aqi + "</div><div class='fc-cat'><span class='catpill " + CAT_CLASS(f.category) + "'>" + f.category + "</span></div>" +
      "<div class='fc-range'>likely " + f.range_low + "\u2013" + f.range_high + "</div><div class='fc-conf'>" + CONF_SHORT[f.tier] + (f.method === "model" ? "" : " \u00b7 persistence") + "</div>" + badge;
    box.appendChild(d);
  });
}

function drawChart(st) {
  const obs = [];                       // break the line where hours are missing (never draw across a data gap)
  st.observed.forEach((o, i) => {
    if (i > 0 && o.x - st.observed[i - 1].x > 1.5) obs.push({ x: (o.x + st.observed[i - 1].x) / 2, y: null });
    obs.push({ x: o.x, y: o.aqi, t: o.t_end });
  });
  const fc24 = st.forecasts.filter((f) => f.horizon <= MAIN_MAX_H);
  const main = fc24.map((f) => ({ x: f.horizon, y: f.aqi, t: f.target_end }));
  const whisk = fc24.map((f) => ({ label: "Likely range", data: [{ x: f.horizon, y: f.range_low, t: f.target_end }, { x: f.horizon, y: f.range_high, t: f.target_end }],
    borderColor: "rgba(255,138,42,0.45)", borderWidth: 4, pointRadius: 0, showLine: true, _w: true }));
  const xmax = Math.max(26, Math.ceil(st.age_hours) + 3);          // up to +24 h; extended just enough to show "now" when the data is older than that
  const ymax = Math.max(60, ...fc24.map((f) => f.range_high), ...obs.filter((o) => o.y != null).map((o) => o.y)) * 1.1;
  const data = { datasets: [
    { label: "Observed AQI", data: obs, borderColor: "#7cc4ff", backgroundColor: "#7cc4ff", pointRadius: 0, borderWidth: 2 },
    { label: "Forecast (+1, +6, +12, +24 h)", data: main, showLine: false, pointRadius: 7, backgroundColor: "#ff8a2a", borderColor: "#ff8a2a" },
    { label: "Now (data is " + Math.round(st.age_hours) + " h old)", data: [{ x: st.age_hours, y: 0 }, { x: st.age_hours, y: ymax }], borderColor: "#ffb27a", borderWidth: 2, pointRadius: 0 },
  ].concat(whisk) };
  const options = { responsive: true, maintainAspectRatio: false, animation: false, parsing: false,
    scales: { x: { type: "linear", min: -96, max: xmax, title: { display: true, text: "Hours after the newest observation (0 = newest observation)" },
                   afterBuildTicks: (axis) => { const t = []; for (let v = -96; v <= axis.max; v += 12) t.push({ value: v }); axis.ticks = t; },
                   ticks: { callback: (v) => (NARROW() && v % 24 !== 0 ? "" : v === 0 ? "last obs" : (v > 0 ? "+" : "") + v + " h"), autoSkip: false, maxRotation: 0, font: { size: NARROW() ? 10 : 12 } } },
              y: { beginAtZero: true, max: Math.ceil(ymax / 20) * 20, title: { display: true, text: "CPCB AQI" } } },
    plugins: { legend: { labels: { filter: (it, d) => !d.datasets[it.datasetIndex]._w || it.datasetIndex === d.datasets.findIndex((x) => x._w) } },
               tooltip: { callbacks: { title: (items) => (items[0].raw.t ? "Hour ending " + items[0].raw.t : ""), label: (it) => it.dataset.label + ": " + rint(it.parsed.y) } } } };
  if (chart) { chart.data = data; chart.options = options; chart.update("none"); } else chart = new Chart($("chart"), { type: "line", data, options });
}

function fillTable(st) {
  const tb = $("fcTable").querySelector("tbody"); tb.innerHTML = "";
  renderExperimental(st.forecasts, () => st.last_aqi);              // persistence = the last observed AQI
  st.forecasts.filter((f) => f.horizon <= MAIN_MAX_H).forEach((f) => {
    const tr = document.createElement("tr");
    tr.innerHTML = "<td>+" + f.horizon + " h</td><td>" + f.target_end + "</td><td>" + fmtH(f.hours_from_now) + "</td><td><b>" + f.aqi +
      "</b><div class='small muted'>likely " + f.range_low + " to " + f.range_high + "</div></td><td>" + catCell(f.category) +
      (f.category_low !== f.category_high ? "<div class='small muted'>likely " + f.category_low + " to " + f.category_high + "</div>" : "") +
      "</td><td>" + (f.method === "model" ? "CSH-AQI model" : "Persistence fallback") + "</td><td>" + TIER[f.tier] + "</td>";
    tb.appendChild(tr);
  });
}

async function advice(st) {
  const p = profile(), t = alertLevelFor(p);
  const stale = st.age_hours > 12;                       // e-mail alerts are paused beyond 12 h; the card turns grey and says "last known"
  $("adviceTitle").textContent = stale ? "Last known conditions" : "Advice for you";
  $("adviceBox").className = stale ? "small advice-stale" : "small";
  $("emailNote").textContent = stale ? "E-mail alerts are paused while data is older than 12 h."
                                     : "E-mail alerts are active while the data is fresher than 12 h.";
  const future = st.forecasts.filter((f) => f.status === "future" && f.horizon <= MAIN_MAX_H);
  const peak = future.reduce((m, f) => (!m || f.aqi > m.aqi ? f : m), null);
  let up = "Upcoming: no forecast for the coming hours: every forecast horizon (up to 24 h) has already passed (the newest data is " + Math.round(st.age_hours) + " h old).";
  if (peak) {
    const where = "AQI " + peak.aqi + " (" + peak.category + ") for the hour ending " + peak.target_end + " (+" + peak.horizon + " h after the last observation), likely " + peak.range_low + " to " + peak.range_high + ".";
    if (stale) {
      // never present a low-confidence forecast, or one built on old data, as an alert
      up = "Tendency only, not an alert: the highest forecast still ahead is " + where;
    } else {
      up = "Upcoming: highest forecast still ahead of now is " + where + " " +
        (peak.aqi >= t ? "This reaches your alert level (AQI " + t + ")." : (peak.range_high >= t ? "It could reach your alert level (AQI " + t + ") at the upper end." : "It stays below your alert level (AQI " + t + ")."));
    }
  }
  // advice basis: the last observation when the data is old (or the forecast is only a tendency); otherwise the higher of last / next-24 h forecast
  const near = future.filter((f) => f.horizon <= 24 && f.tier !== "low");
  const peakNear = near.reduce((m, f) => (!m || f.aqi > m.aqi ? f : m), null);
  let basis = { aqi: st.last_aqi, label: "the last observed AQI (hour ending " + st.last_obs_end + ", " + Math.round(st.age_hours) + " h old)" };
  if (!stale && peakNear && peakNear.aqi >= st.last_aqi) basis = { aqi: peakNear.aqi, label: "the forecast for +" + peakNear.horizon + " h (hour ending " + peakNear.target_end + ")" };
  // trend / best time only from forecasts still ahead and only while the data is fresh (old data: no planning advice)
  const a = await api("/api/advice?aqi=" + basis.aqi, { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ groups: p.groups, alert_from: p.alert_from, forecasts: stale ? [] : near, now_aqi: st.last_aqi,
                           dominant: st.dominant_now || null, station: st.station, last_obs_end: st.last_obs_end }) });
  const pa = a.personal;
  const cls = stale ? "level-stale" : "level-" + a.level;
  // summary first (badge, status, top 3 actions), then "Show all advice"; with old data the status says so and a warning comes first
  const oldNote = stale ? "<p class='wk-stale' role='status'>Last known conditions: recorded " + Math.round(st.age_hours) + " hours ago and may have changed. " +
    "Check a current source before acting.</p>" : "";
  let html = "<p class='upcoming'>" + up + "</p><div class='" + cls + "'>" + oldNote + adviceSummaryHtml(a, pa, "based on " + escHtml(basis.label)) + adviceRestHtml(a, pa);
  html += "<p class='small muted'>Not medical advice; see the disclaimer. In an emergency call 112.</p></div>";
  $("adviceBox").innerHTML = html;
  $("nowAdvice").innerHTML = oldNote + adviceSummaryHtml(a, pa, stale ? "last known conditions, " + Math.round(st.age_hours) + " h old" : "") + adviceRestHtml(a, pa);
}



/* developer test: ?selftest=live reports what the live page shows (strip, tables, chart axis) so a test can verify the +1/+6/+12/+24 h rule */
async function selfTestLive() {
  const x = chart.options.scales.x;
  const fcPoints = chart.data.datasets.filter((d) => !/^(Observed|Now)/.test(d.label)).flatMap((d) => d.data.map((p) => p.x));
  const nowLine = chart.data.datasets.find((d) => /^Now/.test(d.label));
  const out = { mode: "live", cards: $("strip").querySelectorAll(".fc-card").length, stripMessage: ($("strip").querySelector(".strip-msg") || {}).textContent || null,
                mainRows: $("fcTable").querySelectorAll("tbody tr").length, expRows: $("expTable").querySelectorAll("tbody tr").length,
                expHorizons: [...$("expTable").querySelectorAll("tbody tr")].map((r) => r.children[0].textContent),
                chartMaxForecastX: Math.max(...fcPoints), xAxisMax: x.max, nowX: nowLine ? nowLine.data[0].x : null,
                upcoming: ($("adviceBox").querySelector(".upcoming") || {}).textContent || "", severity: $("banner").className };
  const pre = document.createElement("pre"); pre.id = "selftest"; pre.hidden = true; pre.style.display = "none"; pre.setAttribute("aria-hidden", "true"); pre.textContent = JSON.stringify(out);
  document.body.appendChild(pre);
}

/* developer test: ?selftest=sticky scrolls far down and reports where the banner is (it must stay at the top of the window) */
async function selfTestSticky() {
  window.scrollTo(0, 1500);
  await new Promise((r) => setTimeout(r, 400));
  const r = document.getElementById("banner").getBoundingClientRect();
  const out = { mode: "sticky", page: location.pathname, scrollY: Math.round(window.scrollY), bannerTop: Math.round(r.top), bannerBottom: Math.round(r.bottom),
                bannerStaysVisible: Math.abs(r.top - stickyTarget()) < 2 && r.bottom > 0, expectedTop: Math.round(stickyTarget()), bodyOverflowX: getComputedStyle(document.body).overflowX,
                htmlOverflowX: getComputedStyle(document.documentElement).overflowX };
  const pre = document.createElement("pre"); pre.id = "selftest"; pre.hidden = true; pre.style.display = "none"; pre.setAttribute("aria-hidden", "true"); pre.textContent = JSON.stringify(out);
  document.body.appendChild(pre);
}

let initFailed = false;
initServerBar(() => { if (initFailed) location.reload(); });
init().catch((e) => { initFailed = true; $("bannerText").textContent = "Could not start: " + e.message; });
