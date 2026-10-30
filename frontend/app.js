/* AQI forecast website - Replay mode. Plain JavaScript, no framework. */
"use strict";

const DEFAULT_ALERT = { vulnerable: 101, healthy: 201 };
const VULN = ["lung", "heart", "child", "older", "pregnant", "outdoor_worker", "athlete"];
const ALERT_CHOICES = [51, 101, 151, 201, 301];
const TICKS = [-48, -36, -24, -12, 0, 1, 6, 12, 24];
// pop-ups: "likely" up to +24 h, "possible" only up to +12 h, nothing for +36 h and beyond (table only)
const POPUP_MAX_H = { likely: 24, possible: 12 };
const COOLDOWN_MS = 12 * 3600e3;          // simulated time before the same station may alert again at the same or a lower level
const RANK = { none: 0, possible: 1, likely: 2 };
const CAT_ORDER = ["Good", "Satisfactory", "Moderate", "Poor", "Very Poor", "Severe"];
const catRank = (c) => Math.max(CAT_ORDER.indexOf(c), 0);
// the category an alert WARNED about: for a "possible" alert the upper end of its likely range ("could reach ..."), otherwise the forecast category.
// "UPDATE, higher category" is only used when the new alert is above what the previous alert already warned about (fixed 17 Oct 2026).
const warnedRank = (level, f) => Math.max(catRank(f.category), level === "possible" ? catRank(f.category_high) : 0);

const S = { period: null, station: null, hours: [], idx: 0, timer: null, profile: loadProfile(),
            chart: null, reqId: 0, meta: null, alert: null, lastIssued: {}, stats: { shown: 0, replaced: 0, cleared: 0, escalated: 0, requests: 0, dropped: 0 }, renders: 0, shownIdx: 0, playing: false, playToken: 0, pauseOnAlert: true };

const rint = (x) => Math.floor(Number(x) + 0.5);               // same rounding as the server
const tms = (s) => Date.parse(String(s).replace(" ", "T"));      // "YYYY-MM-DD HH:MM[:SS]" -> ms (local clock, consistent use)

/* ---------- profile (localStorage, wrapped: it can be unavailable) ---------- */
function loadProfile() {
  try { const p = JSON.parse(localStorage.getItem("aqiProfile") || "null"); if (p) return p; } catch (e) { /* ignore */ }
  return { groups: [], alert_from: 201 };
}
function saveProfile() {
  if (S.account) return;                     // logged in: the profile lives in the account; never overwrite the guest profile in this browser
  try { localStorage.setItem("aqiProfile", JSON.stringify(S.profile)); } catch (e) { /* ignore */ }
}
function isVulnerable(p) { return (p.groups || []).some((g) => VULN.includes(g)); }
function defaultAlert(p) { return isVulnerable(p) ? DEFAULT_ALERT.vulnerable : DEFAULT_ALERT.healthy; }
function effectiveAlert(p) { return Math.min(p.alert_from, defaultAlert(p), 301); }
function th() { return effectiveAlert(S.profile); }

function renderProfile() {
  document.querySelectorAll("input[name=grp]").forEach((cb) => { cb.checked = S.profile.groups.includes(cb.value); });
  const maxAlert = defaultAlert(S.profile);
  const sel = $("alertFrom");
  sel.innerHTML = "";
  ALERT_CHOICES.filter((v) => v <= maxAlert).forEach((v) => {
    const o = document.createElement("option");
    o.value = v; o.textContent = "AQI " + v + (v === maxAlert ? " (default)" : " (lower than default)");
    sel.appendChild(o);
  });
  S.profile.alert_from = Math.min(S.profile.alert_from, maxAlert);
  sel.value = String(S.profile.alert_from);
  $("thresholdInfo").textContent = (isVulnerable(S.profile)
    ? "Vulnerable profile: advice from AQI 51, alert from AQI 101 by default."
    : "Healthy adult: advice from AQI 101, alert from AQI 201 by default.") +
    " You may lower your alert level, never raise it above the default. Everyone is alerted from AQI 301.";
  saveProfile();
}

/* ---------- API ---------- */
async function api(path, opts) {
  const r = await apiFetch(path, opts);
  if (!r.ok) throw new Error(path + " -> HTTP " + r.status);
  return r.json();
}

/* ---------- start-up ---------- */
async function init() {
  S.meta = await api("/api/meta");
  S.account = await getAccount();                 // logged in -> use the account's own profile (groups incl. age rules, alert level, home station)
  renderAcctNav(S.account);
  if (S.account) S.profile = { groups: S.account.groups, alert_from: S.account.alert_effective, station: S.account.station };
  fillDisclaimer(S.meta);
  const refs = $("refs");
  Object.entries(S.meta.references).forEach(([k, v]) => { const li = document.createElement("li"); li.value = +k; li.textContent = v; refs.appendChild(li); });

  const [stations, periods] = await Promise.all([api("/api/stations"), api("/api/periods")]);
  S.periods = periods.periods;
  const ps = $("period");
  periods.periods.forEach((p) => {
    const o = document.createElement("option");
    o.value = p.key; o.textContent = p.key === "validation" ? "Validation (more events)" : "Test (monsoon, few events)";
    ps.appendChild(o);
  });
  ps.value = new URLSearchParams(location.search).get("period") || periods.default;
  const ss = $("station");
  stations.forEach((s) => { const o = document.createElement("option"); o.value = s.id; o.textContent = s.name; ss.appendChild(o); });
  const urlStation = new URLSearchParams(location.search).get("station");            // developer switch: ?station=mysuru
  ss.value = (urlStation && stations.some((s) => s.id === urlStation)) ? urlStation
    : (S.profile.station && stations.some((s) => s.id === S.profile.station)) ? S.profile.station : "silkboard";

  renderProfile();
  bind();
  if (S.account) applyAccountUi(); else loadServerProfile();
  S.period = ps.value; S.station = ss.value;
  const at = new URLSearchParams(location.search).get("at");          // opened from a push notification: show exactly that alert hour
  if (at) {
    await loadHours(false);
    const i = S.hours.indexOf(at);
    if (i >= 0) { S.idx = i; await show(); }
  } else await loadHours(true);
  if (/[?&]selftest=servernotif/.test(location.search)) await selfTestServerNotif();
  else if (/[?&]selftest=popuplogic/.test(location.search)) await selfTestPopupLogic();
  else if (/[?&]selftest=popup(&|$)/.test(location.search)) await selfTestPopup();
  else if (/[?&]selftest=jump/.test(location.search)) await selfTestJump();
  else if (/[?&]selftest=sticky/.test(location.search)) await selfTestSticky();
  else if (/[?&]selftest=play/.test(location.search)) await selfTestPlay();
  else if (/[?&]selftest=/.test(location.search)) await selfTest();
}

function periodInfo() {
  const p = S.periods.find((x) => x.key === S.period);
  $("periodInfo").textContent = p ? p.label + ". AQI > 100 in " + p.hours_gt100 + " station-hours, > 200 in " + p.hours_gt200 + "." : "";
}

async function loadHours(jumpToFirstEvent) {
  stop();
  clearAlert("context change");
  S.lastIssued = {};
  periodInfo();
  const h = await api("/api/replay/hours?period=" + S.period + "&station=" + S.station);
  S.hours = h.hours;
  $("slider").max = Math.max(S.hours.length - 1, 0);
  S.idx = 0;
  if (jumpToFirstEvent) await jumpToEvent(true); else await show();
}

/* ---------- show one simulated hour ---------- */
/* ---------- one tick = one request = one response = one synchronous render ----------
   Banner, slider, station card, chart, tables, advice and alerts are ALL drawn from the same response in one pass, and every component is
   stamped (data-stamp -> dataset.sim) with the simulated time of that response so a test can prove they always agree.
   A response that is no longer the newest request is dropped (never half-applied). */
async function show() {
  if (!S.hours.length) { $("fcNote").textContent = "No forecasts for this station in this period."; return null; }
  const idx = S.idx, t = S.hours[idx];
  const my = ++S.reqId;
  S.stats.requests++;
  const prof = S.profile;
  const st = await api("/api/replay/state?period=" + S.period + "&station=" + S.station + "&t=" + encodeURIComponent(t) +
    "&groups=" + encodeURIComponent((prof.groups || []).join(",")) + "&alert_from=" + prof.alert_from);
  if (my !== S.reqId) { S.stats.dropped++; return null; }          // superseded / out of order: drop it completely
  render(st, idx);
  return st;
}

function refreshWeekly(st) {
  const t = st.label_time, d = new Date(t.replace(" ", "T"));
  if (+t.slice(11, 13) !== 23) d.setDate(d.getDate() - 1);                     // last complete day before the replay clock
  const key = [st.station, d.toDateString(), (S.profile.groups || []).join(",")].join("|");
  if (key === S.weeklyKey) return;
  S.weeklyKey = key;
  loadWeekly($("weeklyCard"), { station: st.station, mode: "replay", t: t, groups: (S.profile.groups || []).join(",") }, st.station_name);
}
/* "All stations now" card (stations.js): values at the replay clock; clicking a station opens it at the SAME replay hour */
function refreshStations(st) {
  const box = $("stationsCard");
  if (!box || typeof loadStations !== "function") return;
  if (S.stationsKey === st.label_time) {
    if (box._data && box._cur !== st.station) { box._cur = st.station; renderStations(box, box._data, st.station, switchStationKeepTime); }
    return;
  }
  S.stationsKey = st.label_time; box._cur = st.station;
  loadStations(box, { mode: "replay", t: st.label_time }, st.station, switchStationKeepTime);
}
async function switchStationKeepTime(id) {
  if (!id || id === S.station) return;
  const t = S.hours[S.idx];
  stop(); clearAlert("context change"); S.lastIssued = {};
  S.station = id; S.profile.station = id; $("station").value = id; saveProfile();
  const h = await api("/api/replay/hours?period=" + S.period + "&station=" + id);
  S.hours = h.hours; $("slider").max = Math.max(S.hours.length - 1, 0);
  const i = S.hours.findIndex((x) => x >= t);
  S.idx = i < 0 ? Math.max(S.hours.length - 1, 0) : i;
  await show();
  window.scrollTo({ top: 0, behavior: "smooth" });
}
function render(st, idx) {
  const sim = st.sim_time_end;
  S.shownIdx = idx;
  if ($("jumpMsg")) $("jumpMsg").textContent = "";
  $("slider").value = idx;                                          // the slider shows what is DISPLAYED, not what was requested
  S.sliderPending = false;
  $("simTime").textContent = sim + " IST";
  if ($("simTimeShort")) $("simTimeShort").textContent = bannerShort(sim) + " IST";       // phones: "24 Apr, 02:00 IST" (never cut off)
  $("stationTitle").textContent = st.station_name;
  $("nowTime").textContent = sim;
  $("nowAqi").textContent = st.now && st.now.aqi != null ? rint(st.now.aqi) : "n/a";
  renderScale($("nowScale"), st.now && st.now.aqi != null ? rint(st.now.aqi) : null);
  const cat = st.now ? st.now.category : null;
  const pill = $("nowCat");
  pill.textContent = cat || "no valid AQI"; pill.className = "catpill " + CAT_CLASS(cat);
  $("stationCard").className = "card now " + CC(cat);
  $("nowExtra").textContent = st.now && st.now.dominant ? "Main pollutant now: " + pn(st.now.dominant) : "";
  expireAlert(st);                      // stale alerts disappear as soon as simulated time moves past them
  drawChart(st);
  fillForecasts(st);
  fillRealised(st);
  renderStrip(st);
  renderPollutants(st.pollutants, st.now ? st.now.dominant : null);
  refreshWeekly(st);
  refreshStations(st);
  renderAdvice(st);
  renderNowAdvice(st);
  if (st.advice) maybeAlert(st, st.advice);   // alert decision from the SAME response (advice came with it)
  document.querySelectorAll("[data-stamp]").forEach((el) => { el.dataset.sim = sim; });
  S.last = st;
  S.renders++;
  if (S.onRender) S.onRender(st);
}

/* ---------- chart ---------- */
function drawChart(st) {
  const simMs = tms(st.sim_time_end);
  const obs = st.observed.filter((o) => o.aqi != null)
    .map((o) => ({ x: (tms(o.t_end) - simMs) / 3600e3, y: o.aqi, t: o.t_end }));          // x = hours before "now"; last point is exactly 0
  const av = st.forecasts.filter((f) => f.available && f.horizon <= MAIN_MAX_H);
  const main = av.filter((f) => f.confidence === "main").map((f) => ({ x: f.horizon, y: f.aqi, t: f.target_end }));
  const pers = av.map((f) => ({ x: f.horizon, y: f.persistence, t: f.target_end }));
  const a = th();
  const whiskers = av.map((f) => ({ label: "Likely range", data: [{ x: f.horizon, y: f.range_low, t: f.target_end }, { x: f.horizon, y: f.range_high, t: f.target_end }],
    borderColor: "rgba(255,138,42,0.45)", borderWidth: 4, pointRadius: 0, showLine: true, order: 5, _whisker: true }));
  const data = {
    datasets: [
      { label: "Observed AQI", data: obs, borderColor: "#7cc4ff", backgroundColor: "#7cc4ff", pointRadius: 0, borderWidth: 2, tension: 0, order: 2 },
      { label: "Forecast (+1, +6, +12, +24 h)", data: main, showLine: false, pointStyle: "circle", pointRadius: 7, backgroundColor: "#ff8a2a", borderColor: "#ff8a2a", order: 1 },
      { label: "Persistence", data: pers, showLine: false, pointStyle: "crossRot", pointRadius: 6, borderColor: "#9aa8b8", order: 3 },
      { label: "Your alert level (AQI " + a + ")", data: [{ x: -48, y: a }, { x: 26, y: a }], borderColor: "#ffb27a", borderDash: [6, 4], pointRadius: 0, borderWidth: 1.5, order: 4 },
    ].concat(whiskers),
  };
  const options = {
    responsive: true, maintainAspectRatio: false, animation: false, parsing: false,
    scales: {
      x: { type: "linear", min: -48, max: 26, title: { display: true, text: "Hours from simulated now (0 = now). Marks at +1, +6, +12, +24 h" },
           afterBuildTicks: (axis) => { axis.ticks = TICKS.map((v) => ({ value: v })); },
           ticks: { callback: (v) => (NARROW() && !LABEL_SM.includes(v) ? "" : v === 0 ? "now" : v === 1 ? "" : (v > 0 ? "+" : "") + v + " h"), autoSkip: false, maxRotation: 0, font: { size: NARROW() ? 10 : 12 } } },
      y: { beginAtZero: true, title: { display: true, text: "CPCB AQI" } },
    },
    plugins: { legend: { labels: { filter: (it, d) => !d.datasets[it.datasetIndex]._whisker || it.datasetIndex === d.datasets.findIndex((x) => x._whisker) } },
               tooltip: { callbacks: { title: (items) => (items[0].raw.t ? "Hour ending " + items[0].raw.t : ""),
                                       label: (it) => it.dataset.label + ": " + rint(it.parsed.y) } } },
  };
  if (S.chart) { S.chart.data = data; S.chart.options = options; S.chart.update("none"); }
  else S.chart = new Chart($("chart"), { type: "line", data, options });
  S.chartSim = st.sim_time_end;
}

/* ---------- tables ---------- */
const TIER = { high: "High confidence", medium: "Moderate confidence", low: "Low confidence: tendency only" };

function levelBadge(l, h) {
  if (l === "none") return "<span class='muted'>-</span>";
  if (h > POPUP_MAX_H[l]) return "<span class='muted'>" + (l === "likely" ? "Likely level" : "Possible level") + " (not notified)</span>";
  return l === "likely" ? "<b>Likely alert</b>" : "Possible alert";
}
function catCell(c) { return "<span class='catpill " + CAT_CLASS(c) + "'>" + c + "</span>"; }

/* alert level of one forecast against the user's level; uses the DISPLAYED integers */
function alertLevel(f) {
  if (!f.available) return "none";
  const t = th();
  if (f.aqi >= t) return "likely";
  if (f.range_high >= t) return "possible";
  return "none";
}

function fillForecasts(st) {
  const tb = $("fcTable").querySelector("tbody");
  tb.innerHTML = "";
  renderExperimental(st.forecasts, (f) => f.persistence);
  st.forecasts.filter((f) => f.horizon <= MAIN_MAX_H).forEach((f) => {
    const tr = document.createElement("tr");
    if (!f.available) {
      tr.innerHTML = "<td>+" + f.horizon + " h</td><td>" + f.target_end + "</td><td colspan='4' class='muted'>not available (data gap)</td><td>" +
        TIER[f.tier] + "</td><td></td>";
    } else {
      tr.innerHTML = "<td>+" + f.horizon + " h</td><td>" + f.target_end + "</td><td><b>" + f.aqi + "</b><div class='small muted'>likely " +
        f.range_low + " to " + f.range_high + "</div></td><td>" + catCell(f.category) +
        (f.category_low !== f.category_high ? "<div class='small muted'>likely " + f.category_low + " to " + f.category_high + "</div>" : "") +
        "</td><td>" + (f.dominant ? pn(f.dominant) : "-") + "</td><td>" + f.persistence + "</td><td>" + TIER[f.tier] +
        "</td><td>" + levelBadge(alertLevel(f), f.horizon) + "</td>";
    }
    tb.appendChild(tr);
  });
  const n = st.forecasts.filter((f) => f.available && f.horizon <= MAIN_MAX_H).length;
  $("fcNote").textContent = (n === 0 ? "No forecast for this hour (station data incomplete). " : "") +
    "Forecasts exist only at these fixed horizons; hours in between are not forecast.";
}

function fillRealised(st) {
  const tb = $("rzTable").querySelector("tbody");
  tb.innerHTML = "";
  st.realised.filter((r) => r.horizon <= MAIN_MAX_H).forEach((r) => {
    const tr = document.createElement("tr");
    tr.innerHTML = "<td>+" + r.horizon + " h</td><td>" + r.made_at_end + "</td><td>" + r.forecast + "</td><td>" + r.persistence +
      "</td><td><b>" + r.actual + "</b></td>";
    tb.appendChild(tr);
  });
}

/* ---------- advice ("upcoming" line + advice for the highest of now / next 24 h) ---------- */
function upcomingLine(st) {
  const next24 = st.forecasts.filter((f) => f.available && f.confidence === "main");
  if (!next24.length) return "Upcoming: no forecast is available for this hour (data gap).";
  const peak = next24.reduce((m, f) => (f.aqi > m.aqi ? f : m));
  const t = th();
  let s = "Upcoming (next 24 h): highest forecast is AQI " + peak.aqi + " (" + peak.category + ") for the hour ending " + peak.target_end +
    " (+" + peak.horizon + " h), likely " + peak.range_low + " to " + peak.range_high + ". ";
  s += peak.aqi >= t ? "This reaches your alert level (AQI " + t + ")."
     : (peak.range_high >= t ? "It could reach your alert level (AQI " + t + ") at the upper end of the range."
                             : "No forecast within 24 h reaches your alert level (AQI " + t + ").");
  return s;
}

function renderAdvice(st) {
  const box = $("adviceBox");
  const up = "<p class='upcoming'>" + upcomingLine(st) + "</p>";
  const a = st.advice;
  if (!a) { box.className = ""; box.innerHTML = up + "<p>No AQI available for this hour.</p>"; return; }
  // summary first (badge, status, top 3 actions), then "Show all advice" (grouped sections); wording unchanged from the server
  let html = up + "<div class='level-" + a.level + "'>" + adviceSummaryHtml(a, st.personal, "based on " + escHtml(a.basis.label)) + adviceRestHtml(a, st.personal);
  html += "<p class='small muted'>Not medical advice. See the disclaimer below. In an emergency call 112.</p></div>";
  box.className = "";
  box.innerHTML = html;
}

/* ---------- alerts: one small pop-up at a time ---------- */
function candidate(st) {
  let best = null;
  st.forecasts.forEach((f) => {
    const l = alertLevel(f);
    if (l === "none" || f.horizon > POPUP_MAX_H[l]) return;
    if (!best || RANK[l] > RANK[best.level] || (l === best.level && f.aqi > best.f.aqi)) best = { level: l, f };
  });
  return best;
}

/* ---------- alert pop-up lifecycle ----------
   PAUSE ON ALERT (setting, on by default in replay): raising an alert (or an escalation) stops the replay clock and the pop-up has two buttons,
   "Continue replay" and "Dismiss"; it stays until one of them is pressed. With pause off, a pop-up stays visible for at least MIN_VISIBLE_MS of real
   time (or until dismissed or replaced) even if its target hour passes in simulated time: it is then marked "(target hour now passed)" instead of being
   removed. A newer alert replaces a stale pop-up at once; an escalation replaces a live one at once; only one pop-up is shown at a time. */
const MIN_VISIBLE_MS = 10000;

function markStale(why) {                       // keep the pop-up on screen, but say that it no longer applies
  const cur = S.alert;
  if (!cur || cur.stale) return;
  cur.stale = why;
  if (cur.noteEl) { cur.noteEl.textContent = why; cur.noteEl.hidden = false; }
  if (cur.el) cur.el.classList.add("toast-stale");
}

function tryRetire() {                          // remove a stale pop-up once it has been visible long enough (never while pinned by pause-on-alert)
  const cur = S.alert;
  if (!cur || !cur.stale || cur.pinned) return;
  if (Date.now() - cur.shownAt >= MIN_VISIBLE_MS) clearAlert("expired");
}

function expireAlert(st) {
  const cur = S.alert;
  if (!cur) return;
  const simMs = tms(st.sim_time_end);
  if (cur.station !== st.station || simMs < cur.issuedMs) { clearAlert("expired"); return; }   // another station, or time was rewound: it no longer belongs here
  if (simMs >= cur.targetMs) markStale("(target hour now passed)");
  tryRetire();
}

function maybeAlert(st, a) {
  const simMs = tms(st.sim_time_end);
  const c = candidate(st);
  if (!c) { if (S.alert && S.alert.station === st.station) { markStale("(the forecast no longer reaches your alert level)"); tryRetire(); } return; }
  const cr = warnedRank(c.level, c.f);
  // ESCALATION: a higher level (possible -> likely) or a HIGHER CATEGORY than the alert on screen replaces it at once and bypasses the cooldown.
  if (S.alert && !S.alert.stale) {
    const catUp = c.level === "likely" && cr > S.alert.catRank, levelUp = RANK[c.level] > RANK[S.alert.level];
    if (catUp || levelUp) { S.stats.replaced++; S.stats.escalated++; issue(st, c, a, simMs, catUp ? "category" : "level"); }
    return;                                                    // same level and category: keep the current pop-up, no spam
  }
  // no live pop-up (none, or only a stale one that a newer alert simply replaces): apply the cooldown
  const last = S.lastIssued[st.station];
  const catUpLast = last && cr > last.catRank, levelUpLast = last && RANK[c.level] > RANK[last.level];
  if (last && simMs >= last.ms && simMs - last.ms < COOLDOWN_MS && !catUpLast && !levelUpLast) return;   // cooldown (12 h simulated)
  const within = last && simMs >= last.ms && simMs - last.ms < COOLDOWN_MS;
  issue(st, c, a, simMs, within ? (catUpLast ? "category" : "level") : "");
}

function issue(st, c, a, simMs, escalation) {
  clearAlert("replaced");
  const f = c.f, likely = c.level === "likely";
  const title = (escalation === "category" ? "UPDATE, higher category: " : escalation === "level" ? "UPDATE, higher alert level: " : "") + (likely ? "AQI alert (likely): " : "Possible AQI alert: ") + st.station_name;
  const meta = "Issued " + st.sim_time_end + " \u00b7 for " + f.target_end + " (+" + f.horizon + " h)";
  const pa = st.personal;                     // headline (forecast line) + 1-2 profile lines, trend, best time, 1 tip (same alert -> same tip)
  const lines = pa ? pa.short : [];
  const body = (likely ? "Forecast AQI " + f.aqi + " (" + f.category + (f.dominant ? ", mainly " + pn(f.dominant) : "") + ")."
                       : "Forecast AQI " + f.aqi + " (" + f.category + "), could reach " + f.range_high + " (" + f.category_high + "; likely range " + f.range_low + " to " + f.range_high + ").");
  const top = pa ? (pa.top3 || []) : [];                    // pop-up summary: the top 3 actions; the other short lines behind "Show all advice"
  const inTop = new Set(top.flatMap((x) => [x.text, ...(x.covers || [])]));      // a merged group line covers the single ones
  const rest = lines.filter((x) => !inTop.has(x.text));
  const pause = !!S.pauseOnAlert;
  const alert = { station: st.station, level: c.level, catRank: warnedRank(c.level, f), aqi: f.aqi, category: f.category, issuedMs: simMs,
                  targetMs: tms(f.target_end), horizon: f.horizon, title, meta, shownAt: Date.now(), pinned: pause, stale: "", wasPlaying: S.playing };
  S.alert = alert;
  S.lastIssued[st.station] = { ms: simMs, level: c.level, catRank: warnedRank(c.level, f) };
  S.stats.shown++;
  if (pause) stop();                                           // PAUSE ON ALERT: the replay clock stops until the user presses a button
  // Channels: the browser (system) notification when enabled, otherwise the small in-page pop-up. With pause-on-alert the in-page pop-up (it has the
  // buttons) is always shown, and the system notification only when the page is not in front (so the two never overlap).
  let system = false;
  if ("Notification" in window && Notification.permission === "granted" && (!pause || document.hidden)) {
    const first = top[0] || lines[0];
    const extra = first ? " " + first.text + " " + first.source : "";
    try { alert.notif = new Notification(title, { body: meta + ". " + body + extra + " [REPLAY - simulated]", tag: "aqi-alert" }); system = true; } catch (e) { system = false; }
  }
  if (pause || !system) {
    const d = document.createElement("div");
    d.className = "toast toast-" + c.level + " " + CC(f.category); d.setAttribute("role", "alert");    // coloured left edge by category
    d.dataset.aqi = f.aqi; d.dataset.category = f.category; d.dataset.range = f.range_low + "-" + f.range_high; d.dataset.dominant = f.dominant || ""; d.dataset.target = f.target_end; d.dataset.horizon = f.horizon;
    const b = document.createElement("b"); b.id = "toastTitle"; b.textContent = title;
    const m = document.createElement("div"); m.className = "small muted"; m.textContent = meta + " \u00b7 REPLAY";
    const p = document.createElement("div"); p.className = "small"; p.textContent = body;
    const badge = document.createElement("div"); badge.className = "toast-badge";
    badge.innerHTML = catBadge(f.category) + " <span>" + (likely ? "Likely alert" : "Possible alert") + "</span>";
    const ul = document.createElement("div"); ul.className = "toast-scroll";
    ul.innerHTML = (top.length ? "<p class='adv-h'>Your top 3 actions</p>" : "") + topActionsHtml(top, pa, "toast-lines small") +
      (rest.length ? "<details class='toast-more'><summary>Show all advice</summary><ul class='toast-lines small'>" +
        rest.map((x) => "<li class='" + paClass(x) + "'>" + personalLine(x) + (x.kind === "best_time" ? howHtml(pa) : "") + "</li>").join("") + "</ul></details>" : "");
    const note = document.createElement("div"); note.className = "small stale-note"; note.hidden = true;
    const actions = document.createElement("div"); actions.className = "toast-actions";
    if (pause) {
      const go = document.createElement("button"); go.type = "button"; go.id = "toastContinue"; go.textContent = "Continue replay";
      go.onclick = () => { clearAlert("continue"); play(); };
      actions.appendChild(go);
    }
    const x = document.createElement("button"); x.type = "button"; x.id = "toastDismiss"; x.className = "secondary"; x.textContent = "Dismiss";
    x.onclick = () => clearAlert("dismissed");
    actions.appendChild(x);
    d.append(b, m, badge, p, ul, note, actions);
    $("toasts").appendChild(d);
    alert.el = d; alert.noteEl = note;
  }
  syncAlertModal();
  alert.channel = system ? "system" : "page";
  alert.timer = setTimeout(() => { if (S.alert === alert) tryRetire(); }, MIN_VISIBLE_MS + 50);   // retire even if no further tick arrives
  alert.lines = lines.map((x) => x.text);
  if (($("emailReplay") && $("emailReplay").checked) || (S.account && S.account.replay_whatsapp)) sendReplayEmail(escalation, S.hours[S.shownIdx], S.period, S.station);
}

function clearAlert(why) {
  const cur = S.alert;
  if (!cur) { $("toasts").innerHTML = ""; return; }
  if (cur.timer) clearTimeout(cur.timer);
  if (cur.el) cur.el.remove();
  if (cur.notif) { try { cur.notif.close(); } catch (e) { /* ignore */ } }
  $("toasts").innerHTML = "";
  S.alert = null;
  if (why !== "replaced" && why !== "context change") S.stats.cleared++;
  syncAlertModal();
}

/* While the replay is paused for an alert (pinned pop-up) it is a modal dialog: centred with a dimmed backdrop on desktop, a bottom sheet on phones.
   Focus moves to "Continue replay" and stays inside the dialog; Esc works like "Dismiss"; focus returns where it was when the dialog closes.
   Without pause-on-alert (or after Play) the pop-up stays the small corner card. */
function syncAlertModal() {
  const box = $("toasts"), a = S.alert;
  const on = !!(a && a.pinned && a.el && box.contains(a.el));
  const was = box.classList.contains("modal");
  box.classList.toggle("modal", on);
  if (on && !was) {
    S.modalReturn = document.activeElement;
    a.el.setAttribute("role", "alertdialog"); a.el.setAttribute("aria-modal", "true"); a.el.setAttribute("aria-labelledby", "toastTitle");
    const first = a.el.querySelector("#toastContinue") || a.el.querySelector("button");
    if (first) first.focus({ preventScroll: true });
  } else if (!on && was) {
    if (a && a.el) { a.el.setAttribute("role", "alert"); a.el.removeAttribute("aria-modal"); }
    const back = S.modalReturn; S.modalReturn = null;
    if (back && document.contains(back) && typeof back.focus === "function") back.focus({ preventScroll: true });
  }
}
document.addEventListener("keydown", (e) => {
  const box = $("toasts");
  if (!box || !box.classList.contains("modal") || !S.alert || !S.alert.el) return;
  if (e.key === "Escape") { e.preventDefault(); clearAlert("dismissed"); return; }
  if (e.key === "Tab") {                                     // keep keyboard focus inside the dialog
    const f = Array.from(S.alert.el.querySelectorAll("button, summary, a[href]")).filter((x) => x.offsetParent !== null);
    if (!f.length) return;
    const i = f.indexOf(document.activeElement), n = f.length;
    if (e.shiftKey && (i <= 0)) { e.preventDefault(); f[n - 1].focus(); } else if (!e.shiftKey && (i === n - 1 || i < 0)) { e.preventDefault(); f[0].focus(); }
  }
});

/* ---------- controls ---------- */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
function stop() { S.playToken = (S.playToken || 0) + 1; S.playing = false; $("play").textContent = "Play"; }
async function play() {
  if (S.playing) { stop(); return; }
  if (S.alert) { S.alert.pinned = false; tryRetire(); syncAlertModal(); }   // playing again: a pinned pop-up now follows the normal rules
  S.playing = true;
  $("play").textContent = "Pause";
  const token = (S.playToken = (S.playToken || 0) + 1), perSec = +$("speed").value;
  // sequential: the next tick starts only after the previous one has been DISPLAYED (no overlapping requests, so the display can never
  // run ahead of or behind the data); a slow server just slows playback down
  while (S.playToken === token) {
    const t0 = Date.now();
    if (S.idx >= S.hours.length - 1) { stop(); break; }
    S.idx = Math.min(S.idx + perSec, S.hours.length - 1);
    try { await show(); } catch (e) { stop(); break; }
    const wait = 1000 - (Date.now() - t0);
    if (wait > 0) await sleep(wait);
  }
}
/* "Skip to next pollution event (demo)": looks ahead (a demo shortcut, not part of any forecast). Events are ONSETS (see backend find_onsets):
   the AQI reaching your alert level, or the CPCB category rising to Moderate or worse. Rules: search only FORWARD from the displayed hour; land
   6 h before the onset (the first available simulated hour at or after onset - 6 h, always before the onset itself); an onset whose lead hour
   is not after the displayed hour is skipped (never jump backwards or stay); if there is none, say so and do not move. */
const JUMP_LEAD_MS = 6 * 3600e3;
function pickJump(onsets, hours, curIdx) {
  for (const o of onsets) {
    const on = tms(o.t);
    const k = hours.findIndex((h) => tms(h) >= on - JUMP_LEAD_MS && tms(h) < on);
    if (k > curIdx) return { k, onset: o };
  }
  return null;
}
async function jumpToEvent(auto) {
  const curIdx = auto ? -1 : S.shownIdx;
  $("jumpMsg").textContent = "";
  const r = await api("/api/replay/events?period=" + S.period + "&station=" + S.station + "&alert_from=" + th());
  const pick = pickJump(r.onsets, S.hours, curIdx);
  if (!pick) {
    if (auto) await show(); else $("jumpMsg").textContent = "No more events in this period";
    return null;
  }
  S.idx = pick.k;
  clearAlert("jump");
  await show();
  S.lastJump = pick.onset;
  return pick.onset;
}

/* ---------- weather-app style views (presentation only; all numbers come from the same response) ---------- */
function renderStrip(st) {
  const box = $("strip");
  box.innerHTML = "";
  st.forecasts.filter((f) => f.horizon <= MAIN_MAX_H).forEach((f) => {
    const d = document.createElement("div");
    d.setAttribute("role", "listitem");
    const head = "<div class='fc-h'>+" + f.horizon + " h</div><div class='fc-t'>" + shortTime(f.target_end) + "</div>";
    if (!f.available) {
      d.className = "fc-card nodata";
      d.innerHTML = head + "<div class='fc-nodata'>not available (data gap)</div>";
    } else {
      const lv = alertLevel(f), tend = f.horizon > 24;
      d.className = "fc-card " + CC(f.category) + (tend ? " tendency" : "");
      d.dataset.aqi = f.aqi; d.dataset.category = f.category; d.dataset.range = f.range_low + "-" + f.range_high; d.dataset.dominant = f.dominant || ""; d.dataset.target = f.target_end; d.dataset.horizon = f.horizon;
      let badge = "";
      if (lv !== "none") {
        const notified = f.horizon <= POPUP_MAX_H[lv];
        badge = "<div><span class='fc-badge " + (lv === "possible" ? "possible " : "") + (notified ? "" : "quiet") + "' title='" +
          (notified ? "Reaches your alert level" : "Reaches your alert level, but nothing is notified at this horizon") + "'>&#9888; " +
          (lv === "likely" ? "Likely" : "Possible") + (notified ? "" : " (not notified)") + "</span></div>";
      }
      d.innerHTML = head + "<div class='fc-aqi'>" + f.aqi + "</div><div class='fc-cat'><span class='catpill " + CAT_CLASS(f.category) + "'>" + f.category + "</span></div>" +
        "<div class='fc-range'>likely " + f.range_low + "\u2013" + f.range_high + "</div><div class='fc-conf'>" + CONF_SHORT[f.tier] + "</div>" + badge;
    }
    box.appendChild(d);
  });
}

function renderNowAdvice(st) {
  const el = $("nowAdvice"), a = st.advice, pa = st.personal;
  if (!a || !pa) { el.textContent = "No AQI available for this hour."; return; }
  el.innerHTML = adviceSummaryHtml(a, pa) + adviceRestHtml(a, pa);         // badge + status, top 3 actions, then "Show all advice"
}

function bind() {
  bindUi(() => { if (S.chart) S.chart.resize(); });
  $("period").onchange = () => { S.period = $("period").value; loadHours(true); };
  $("station").onchange = () => { S.station = $("station").value; S.profile.station = S.station; saveProfile(); loadHours(true); };
  $("slider").oninput = () => { stop(); S.idx = +$("slider").value; S.sliderPending = true; clearAlert("scrub"); show(); };
  $("play").onclick = play;
  $("prev").onclick = () => { stop(); S.idx = Math.max(S.shownIdx - 1, 0); show(); };
  $("next").onclick = () => { stop(); S.idx = Math.min(S.shownIdx + 1, S.hours.length - 1); show(); };
  $("speed").onchange = () => { if (S.playing) { stop(); play(); } };
  $("jumpEvent").onclick = () => { stop(); jumpToEvent(false); };
  document.querySelectorAll("input[name=grp]").forEach((cb) => {
    cb.onchange = () => {
      S.profile.groups = Array.from(document.querySelectorAll("input[name=grp]:checked")).map((x) => x.value);
      S.profile.alert_from = defaultAlert(S.profile);   // changing the profile resets to its default level
      S.lastIssued = {}; clearAlert("profile"); renderProfile(); show();
    };
  });
  $("alertFrom").onchange = () => { S.profile.alert_from = +$("alertFrom").value; S.lastIssued = {}; clearAlert("profile"); saveProfile(); show(); };
  let storedPause = "1";
  try { storedPause = localStorage.getItem("aqiPauseOnAlert") || "1"; } catch (e) { /* ignore */ }
  const urlPause = new URLSearchParams(location.search).get("pauseonalert");
  S.pauseOnAlert = urlPause != null ? urlPause === "1" : storedPause === "1";
  $("pauseOnAlert").checked = S.pauseOnAlert;
  $("pauseOnAlert").onchange = () => { S.pauseOnAlert = $("pauseOnAlert").checked; try { localStorage.setItem("aqiPauseOnAlert", S.pauseOnAlert ? "1" : "0"); } catch (e) { /* ignore */ } };
  $("saveServerProfile").onclick = async () => { try { await saveServerProfile(); } catch (e) { $("emailStatus").textContent = "Not saved: " + e.message; } };
  $("demoProfile").onclick = () => {
    S.profile = { groups: ["lung"], alert_from: 101, station: S.station };
    S.lastIssued = {}; clearAlert("profile"); renderProfile(); show();
  };
  $("enableNotif").onclick = async () => {
    if (!("Notification" in window)) { $("notifStatus").textContent = "This browser does not support notifications. In-page alerts are still shown."; return; }
    const r = await Notification.requestPermission();
    $("notifStatus").textContent = r === "granted" ? "Browser notifications enabled (they are labelled REPLAY)." :
      "Notifications not allowed. In-page alerts are still shown.";
  };
  if ("Notification" in window && Notification.permission === "granted") $("notifStatus").textContent = "Browser notifications enabled.";
  $("testNotif").onclick = testNotification;
}

/* "Test notification": sends one harmless test notification so the user can see how alerts will look. Never counts as an alert. */
async function testNotification() {
  const say = (t) => { $("notifStatus").textContent = t; };
  const inPage = (why) => {                                    // fallback: a small in-page toast, so the button always shows something
    const d = document.createElement("div"); d.className = "toast toast-possible"; d.setAttribute("role", "status");
    const b = document.createElement("b"); b.textContent = "Test notification";
    const p = document.createElement("div"); p.className = "small"; p.textContent = "This is only a test. No air-quality alert. " + why;
    d.append(b, p); $("toasts").appendChild(d); setTimeout(() => d.remove(), 6000);
  };
  if (!("Notification" in window)) { say("This browser does not support notifications. Showing the test in the page instead."); inPage("(browser notifications are not supported)"); return; }
  let perm = Notification.permission;
  if (perm === "default") perm = await Notification.requestPermission();
  if (perm !== "granted") {
    say("Notifications are blocked for this site (browser setting). Showing the test in the page instead; alerts will also appear in the page.");
    inPage("(browser notifications are blocked)"); return;
  }
  try {
    new Notification("Test notification - Karnataka AQI", { body: "This is only a test. If you can see this, alert notifications will appear like this.", tag: "aqi-test" });
    say("Test notification sent. If you did not see it, check the Windows Focus / Do Not Disturb setting.");
  } catch (e) { say("The browser refused to show a notification (" + e.message + "). Showing the test in the page instead."); inPage("(notification failed)"); }
}



/* ?selftest=popuplogic : deterministic test of the pop-up lifecycle with synthetic states and a CONTROLLABLE clock (Date.now is replaced), so
   "visible at 9.8 s, gone at 10.1 s" can be checked exactly. Results are verified by backend/test_alert_popup.py. */
async function selfTestPopupLogic() {
  const results = [], chk = (name, ok, extra) => results.push({ name, ok: !!ok, extra: extra || "" });
  const realNow = Date.now.bind(Date);
  const T0 = 1700000000000; let clock = T0; Date.now = () => clock;
  S.profile = { groups: ["lung"], alert_from: 101, station: "silkboard" };
  const advice = { items: [{ text: "Use face masks.", source: "[3]" }] };
  const mkSt = (simEnd, horizon, aqi, cat) => ({ station: "silkboard", station_name: "Silk Board, Bengaluru", sim_time_end: simEnd,
    forecasts: [{ horizon, available: true, aqi, category: cat, range_low: aqi - 5, range_high: aqi + 5, target_end: fmtMs(tms(simEnd) + horizon * 3600e3), dominant: "pm25", tier: "high", confidence: "main", persistence: aqi }] });
  const reset = (pause) => { clearAlert("test"); S.lastIssued = {}; S.pauseOnAlert = pause; stop(); S.playing = false; clock = T0; };
  const toasts = () => $("toasts").children.length;
  const A10 = mkSt("2026-04-24 10:00", 1, 150, "Moderate"), A11 = mkSt("2026-04-24 11:00", 1, 150, "Moderate");

  // pause OFF: minimum visible time
  reset(false); maybeAlert(A10, advice);
  chk("L1 an alert raises one pop-up", !!S.alert && toasts() === 1);
  chk("L2 pause off: only a Dismiss button (no Continue)", !$("toastContinue") && !!$("toastDismiss"));
  clock = T0 + 1000; expireAlert(A11);
  chk("L3 its target hour passes after 1 s: pop-up stays, marked '(target hour now passed)'", !!S.alert && S.alert.stale === "(target hour now passed)" && $("toasts").textContent.includes("(target hour now passed)") && toasts() === 1);
  clock = T0 + 9800; expireAlert(A11);
  chk("L4 still visible at 9.8 s", !!S.alert && toasts() === 1);
  clock = T0 + 10100; expireAlert(A11);
  chk("L5 removed once 10 s have passed", !S.alert && toasts() === 0);

  // a newer alert replaces a stale pop-up immediately
  reset(false); maybeAlert(A10, advice);
  clock = T0 + 2000; const later = mkSt("2026-04-25 02:00", 1, 150, "Moderate"); expireAlert(later); maybeAlert(later, advice);
  chk("L6 a newer alert replaces the stale pop-up at once (age 2 s), still one pop-up", !!S.alert && S.alert.issuedMs === tms("2026-04-25 02:00") && toasts() === 1);

  // escalation replaces a live pop-up immediately
  reset(false); maybeAlert(mkSt("2026-04-24 10:00", 6, 150, "Moderate"), advice);
  clock = T0 + 2000; const esc = mkSt("2026-04-24 11:00", 1, 250, "Poor"); expireAlert(esc); maybeAlert(esc, advice);
  chk("L7 an escalation (Moderate -> Poor) replaces the live pop-up at once", !!S.alert && S.alert.category === "Poor" && S.alert.title.includes("UPDATE, higher category") && toasts() === 1);

  // pause ON
  reset(true); S.playing = true; maybeAlert(A10, advice);
  chk("L8 pause on: raising an alert stops the replay clock", S.playing === false);
  chk("L9 pause on: the pop-up has 'Continue replay' and 'Dismiss'", !!$("toastContinue") && $("toastContinue").textContent === "Continue replay" && !!$("toastDismiss") && $("toastDismiss").textContent === "Dismiss");
  clock = T0 + 120000; expireAlert(mkSt("2026-04-24 12:00", 1, 150, "Moderate"));
  chk("L10 pause on: the pop-up is pinned (still there after 2 minutes, marked passed)", !!S.alert && !!S.alert.stale && toasts() === 1);
  $("toastContinue").click();
  chk("L11 'Continue replay' removes the pop-up and restarts the clock", !S.alert && toasts() === 0 && S.playing === true);
  stop();

  reset(true); S.playing = true; maybeAlert(A10, advice);
  $("toastDismiss").click();
  chk("L12 'Dismiss' removes the pop-up and the replay stays paused", !S.alert && toasts() === 0 && S.playing === false);

  reset(true); S.playing = true; maybeAlert(A10, advice);
  play();
  chk("L13 pressing Play while a pause pop-up is up counts as continuing (the pop-up is unpinned)", S.alert && S.alert.pinned === false);
  stop(); clearAlert("test");

  // UPDATE label rules (17 Oct 2026, Mysuru 20 Apr report): "higher category" only when above what the previous alert already warned about
  const mkF = (simEnd, horizon, aqi, cat, lo, hi, catHi) => ({ station: "silkboard", station_name: "Silk Board, Bengaluru", sim_time_end: simEnd,
    forecasts: [{ horizon, available: true, aqi, category: cat, range_low: lo, range_high: hi, category_low: cat, category_high: catHi, target_end: fmtMs(tms(simEnd) + horizon * 3600e3), dominant: "pm25", tier: "high", confidence: "main", persistence: aqi }] });
  const titleOf = () => (S.alert ? S.alert.title : "");
  reset(false); maybeAlert(mkF("2026-04-20 07:00", 12, 89, "Satisfactory", 80, 132, "Moderate"), advice);
  chk("M1 setup: a Possible alert (89 Satisfactory, could reach 132 Moderate) is on screen", S.alert && S.alert.level === "possible" && !/UPDATE/.test(titleOf()), titleOf());
  maybeAlert(mkF("2026-04-20 13:00", 6, 132, "Moderate", 120, 150, "Moderate"), advice);
  chk("M2 Possible(could reach Moderate) -> Likely Moderate says 'higher alert level', NOT 'higher category'", /^UPDATE, higher alert level/.test(titleOf()), titleOf());
  reset(false); maybeAlert(mkF("2026-04-20 13:00", 6, 132, "Moderate", 120, 150, "Moderate"), advice);
  maybeAlert(mkF("2026-04-20 14:00", 5, 140, "Moderate", 125, 155, "Moderate"), advice);
  chk("M3 Likely Moderate -> Likely Moderate: no UPDATE, no new pop-up", S.alert && !/UPDATE/.test(titleOf()) && S.alert.aqi === 132 && toasts() === 1, titleOf());
  maybeAlert(mkF("2026-04-20 15:00", 4, 250, "Poor", 230, 270, "Poor"), advice);
  chk("M4 Likely Moderate -> Likely Poor says 'higher category'", /^UPDATE, higher category/.test(titleOf()), titleOf());
  reset(false); maybeAlert(mkF("2026-04-20 13:00", 6, 132, "Moderate", 120, 150, "Moderate"), advice);
  clearAlert("dismissed"); clock = T0 + 60000;
  maybeAlert(mkF("2026-04-20 16:00", 3, 150, "Moderate", 130, 170, "Moderate"), advice);
  chk("M5 after dismissal, same category inside the cooldown: no new pop-up", !S.alert);
  maybeAlert(mkF("2026-04-20 17:00", 2, 320, "Very Poor", 300, 340, "Very Poor"), advice);
  chk("M6 after dismissal, a higher category inside the cooldown is labelled 'higher category'", /^UPDATE, higher category/.test(titleOf()), titleOf());
  reset(false); maybeAlert(mkF("2026-04-20 07:00", 12, 89, "Satisfactory", 80, 260, "Poor"), advice);
  maybeAlert(mkF("2026-04-20 08:00", 6, 250, "Poor", 230, 270, "Poor"), advice);
  chk("M7 Possible that warned 'could reach Poor' -> Likely Poor is a level change only", /^UPDATE, higher alert level/.test(titleOf()), titleOf());

  Date.now = realNow;
  const pre = document.createElement("pre"); pre.id = "selftest"; pre.hidden = true; pre.style.display = "none"; pre.setAttribute("aria-hidden", "true");
  pre.textContent = JSON.stringify({ mode: "popuplogic", results });
  document.body.appendChild(pre);
}

/* ?selftest=popup&mode=pause|nopause&speed=1&seconds=60&start=...  : REAL playback (Silk Board, lung profile at 101)
   pause   : the first alert must stop the clock, hold it for 10 s with both buttons, then Continue restarts it; at the next alert Dismiss must leave it paused
   nopause : record every pop-up episode (how long it was visible, how it ended, whether it was marked when its target hour passed) */
async function selfTestPopup() {
  const q = new URLSearchParams(location.search), mode = q.get("mode") || "nopause", speed = +(q.get("speed") || 1), seconds = +(q.get("seconds") || 60);
  S.profile = { groups: ["lung"], alert_from: 101, station: S.station }; renderProfile();
  S.pauseOnAlert = mode === "pause";
  $("speed").value = String(speed);
  const startAt = q.get("start");
  if (startAt) { const k = S.hours.findIndex((h) => h >= startAt); if (k >= 0) S.idx = k; }
  await show(); play();
  const tick = async (n) => { for (let i = 0; i < n; i++) await sleep(200); };
  const waitFor = async (cond, maxSeconds) => { for (let i = 0; i < maxSeconds * 5; i++) { if (cond()) return true; await sleep(200); } return false; };
  const out = { mode, speed };
  if (mode === "pause") {
    out.alertRaised = await waitFor(() => S.alert && !S.playing, 120);
    out.pausedAtIdx = S.shownIdx;
    out.title = S.alert ? S.alert.title : null;
    out.buttons = { continue: !!$("toastContinue"), dismiss: !!$("toastDismiss") };
    let moved = false, toastGone = false, playingAgain = false;
    for (let i = 0; i < 50; i++) {                                        // 10 s of (virtual) time with the pop-up up
      if (S.shownIdx !== out.pausedAtIdx) moved = true;
      if (!S.alert || !$("toasts").children.length) toastGone = true;
      if (S.playing) playingAgain = true;
      await sleep(200);
    }
    out.held10s = { moved, toastGone, playingAgain };
    $("toastContinue").click();
    out.afterContinue = { toasts: $("toasts").children.length, playing: S.playing };
    const idx0 = S.shownIdx; await tick(15);
    out.advancedAfterContinue = S.shownIdx > idx0;
    out.secondAlert = await waitFor(() => S.alert && !S.playing, 120);
    if (out.secondAlert) {
      const i2 = S.shownIdx; $("toastDismiss").click();
      out.afterDismiss = { toasts: $("toasts").children.length, playing: S.playing };
      await tick(15);
      out.stayedPausedAfterDismiss = S.shownIdx === i2 && !S.playing;
    }
  } else {
    const eps = []; let cur = null;
    for (let i = 0; i < seconds * 5; i++) {
      await sleep(200);
      const a = S.alert, key = a ? a.issuedMs + "|" + a.aqi : null;
      if (cur && cur.key !== key) { cur.end = i; cur.endedBy = key ? "replaced" : "retired"; eps.push(cur); cur = null; }
      if (a && !cur) cur = { key, start: i, staleSamples: 0, marked: true, title: a.title };
      if (cur && a && a.stale) { cur.staleSamples++; if (!$("toasts").textContent.includes(a.stale)) cur.marked = false; }
    }
    if (cur) { cur.end = seconds * 5; cur.endedBy = "still visible"; eps.push(cur); }
    out.episodes = eps.map((e) => ({ title: e.title, visibleSeconds: Math.round((e.end - e.start) * 2) / 10, endedBy: e.endedBy, staleSeconds: Math.round(e.staleSamples * 2) / 10, marked: e.marked }));
  }
  stop();
  const pre = document.createElement("pre"); pre.id = "selftest"; pre.hidden = true; pre.style.display = "none"; pre.setAttribute("aria-hidden", "true");
  pre.textContent = JSON.stringify(out);
  document.body.appendChild(pre);
}

/* ?selftest=servernotif : (a) Test notification with a stubbed window.Notification (granted / denied / unsupported / default->granted);
   (b) the red "Server not running" bar appears when fetch fails and disappears when the server answers again. Verified by backend/test_server_bar.py. */
async function selfTestServerNotif() {
  const results = [], chk = (name, ok, extra) => results.push({ name, ok: !!ok, extra: extra || "" });
  const RealN = window.Notification, realFetch = window.fetch;
  const sent = [];
  const stub = (perm, req) => { function N(title, o) { sent.push({ title, body: o && o.body }); } N.permission = perm; N.requestPermission = async () => { N.permission = req || perm; return N.permission; }; return N; };
  const setN = (N) => { Object.defineProperty(window, "Notification", { value: N, configurable: true, writable: true }); };
  const status = () => $("notifStatus").textContent, toasts = () => $("toasts").textContent;
  chk("N0 the Test notification button exists in the settings drawer", !!$("testNotif") && /Test notification/.test($("testNotif").textContent));
  sent.length = 0; setN(stub("granted")); $("testNotif").click(); await sleep(50);
  chk("N1 granted: one test notification is sent and the status says so", sent.length === 1 && /Test notification/.test(sent[0].title) && /Test notification sent/.test(status()), status());
  chk("N2 the test does not count as an alert", !S.alert);
  $("toasts").innerHTML = ""; sent.length = 0; setN(stub("denied")); $("testNotif").click(); await sleep(50);
  chk("N3 blocked: no system notification, the status explains and an in-page test toast is shown", sent.length === 0 && /blocked/.test(status()) && /only a test/.test(toasts()), status());
  $("toasts").innerHTML = ""; sent.length = 0; setN(stub("default", "granted")); $("testNotif").click(); await sleep(50);
  chk("N4 permission not asked yet: it asks, and sends the test once granted", sent.length === 1, status());
  $("toasts").innerHTML = ""; sent.length = 0; setN(stub("default", "denied")); $("testNotif").click(); await sleep(50);
  chk("N5 permission refused when asked: in-page fallback", sent.length === 0 && /only a test/.test(toasts()), status());
  $("toasts").innerHTML = ""; delete window.Notification; $("testNotif").click(); await sleep(50);
  chk("N6 unsupported browser: in-page fallback with an explanation", /not support/.test(status()) && /only a test/.test(toasts()), status());
  if (RealN) setN(RealN);
  $("toasts").innerHTML = "";

  const bar = () => document.getElementById("serverDown");
  chk("S0 the bar exists and is hidden while the server answers", bar() && bar().hidden === true);
  window.fetch = async () => { throw new TypeError("Failed to fetch"); };
  let threw = false; try { await api("/api/meta"); } catch (e) { threw = true; }
  chk("S1 a failed request throws and shows the red 'Server not running' bar", threw && !bar().hidden && /Server not running/.test(bar().textContent), bar().textContent);
  chk("S2 the bar tells how to start the server", bar().textContent.includes("python -m uvicorn backend.app:app --port 8000"));
  const cs = getComputedStyle(bar());
  chk("S3 the bar is red and stays at the top", cs.backgroundColor === "rgb(183, 28, 28)" && (cs.position === "sticky" || cs.position === "fixed"), cs.backgroundColor + " " + cs.position);
  window.fetch = realFetch;
  await sleep(3500);                                              // the 3-second health check finds the server again
  chk("S4 when the server answers again the bar hides by itself", bar().hidden === true);
  window.fetch = async () => ({ ok: false, status: 500, json: async () => ({}) });
  try { await api("/api/meta"); } catch (e) { /* expected */ }
  chk("S5 an HTTP error (server running) does NOT show 'Server not running'", bar().hidden === true);
  window.fetch = realFetch;
  const pre = document.createElement("pre"); pre.id = "selftest"; pre.hidden = true; pre.style.display = "none"; pre.setAttribute("aria-hidden", "true");
  pre.textContent = JSON.stringify({ mode: "servernotif", results });
  document.body.appendChild(pre);
}

/* ?selftest=jump&station=silkboard&profile=lung|healthy&period=validation&starts=2026-04-19 09:00:00|...&chain=6
   From each start hour press "Skip to next pollution event" up to `chain` times and record every from/to pair (verified against the database by backend/test_jump.py) */
async function selfTestJump() {
  const q = new URLSearchParams(location.search);
  const starts = (q.get("starts") || "").split("|").filter(Boolean), chain = +(q.get("chain") || 6);
  const pr = q.get("profile");
  // alert level can only be LOWERED from the profile's default (lung 101, healthy 201); th() enforces that
  const PROFILES = { healthy: { groups: [], alert_from: 201 }, healthy151: { groups: [], alert_from: 151 }, lung51: { groups: ["lung"], alert_from: 51 } };
  S.profile = Object.assign({ groups: ["lung"], alert_from: 101, station: S.station }, PROFILES[pr] || {});
  renderProfile();
  const results = [];
  for (const start of starts) {
    const k0 = S.hours.findIndex((h) => h >= start);
    if (k0 < 0) continue;
    S.idx = k0; await show();
    for (let i = 0; i < chain; i++) {
      const from = S.hours[S.shownIdx];
      await jumpToEvent(false);
      const to = S.hours[S.shownIdx];
      const moved = to !== from;
      results.push({ start, step: i, from, to, moved, msg: $("jumpMsg").textContent, onset: moved && S.lastJump ? S.lastJump.t : null });
      if (!moved) break;
    }
  }
  const out = { mode: "jump", station: S.station, period: S.period, level: th(), results };
  const pre = document.createElement("pre"); pre.id = "selftest"; pre.hidden = true; pre.style.display = "none"; pre.setAttribute("aria-hidden", "true"); pre.textContent = JSON.stringify(out);
  document.body.appendChild(pre);
}

/* ---------- self tests (developer only) ----------
   ?selftest=1&speed=S&steps=N        steps the player without timers (alert rules, table rows, categories)
   ?selftest=play&speed=S&seconds=N&latency=MS&scrub=1   REAL playback loop with random response delays (out-of-order responses) and user scrubbing,
                                                         checking after every render and every 200 ms that all components show the same hour */
const z2 = (n) => String(n).padStart(2, "0");
const fmtMs = (ms) => { const d = new Date(ms); return d.getFullYear() + "-" + z2(d.getMonth() + 1) + "-" + z2(d.getDate()) + " " + z2(d.getHours()) + ":" + z2(d.getMinutes()); };
const fmtEnd = (label) => fmtMs(tms(label) + 3600e3);                       // hour-START label -> hour-END display string

function checkConsistent() {
  const bad = [];
  if (!S.last) return bad;
  const sim = S.last.sim_time_end;
  document.querySelectorAll("[data-stamp]").forEach((el) => { if (el.dataset.sim !== sim) bad.push("stamp " + (el.id || el.className) + "=" + el.dataset.sim + " vs " + sim); });
  if ($("simTime").textContent !== sim + " IST") bad.push("banner '" + $("simTime").textContent + "' vs " + sim);
  if ($("nowTime").textContent !== sim) bad.push("card '" + $("nowTime").textContent + "' vs " + sim);
  const fromSlider = fmtEnd(S.hours[+$("slider").value]);
  if (!S.sliderPending && fromSlider !== sim) bad.push("slider shows " + fromSlider + " vs " + sim);
  if (S.chartSim !== sim) bad.push("chart " + S.chartSim + " vs " + sim);
  const row = $("fcTable").querySelector("tbody tr");                       // first row = +1 h: its target hour must be the displayed hour + 1 h
  if (row && row.children[1].textContent !== fmtMs(tms(S.hours[S.shownIdx]) + 2 * 3600e3)) bad.push("table row +1 h shows " + row.children[1].textContent);
  if (S.alert && S.alert.issuedMs > tms(sim)) bad.push("alert issued in the future of the displayed hour");
  return bad;
}

async function selfTestPlay() {
  const q = new URLSearchParams(location.search);
  const speed = +(q.get("speed") || 6), seconds = +(q.get("seconds") || 30), latency = +(q.get("latency") || 0), scrub = q.get("scrub") === "1";
  S.pauseOnAlert = q.get("pauseonalert") === "1";
  S.profile = { groups: ["lung"], alert_from: 101, station: S.station }; renderProfile();
  const startAt = q.get("start");
  if (startAt) { const k = S.hours.findIndex((h) => h >= startAt); if (k >= 0) S.idx = k; }
  $("speed").value = String(speed);
  const realApi = api;
  api = async (path, opts) => { if (latency > 0 && path.startsWith("/api/replay/state")) await sleep(Math.random() * latency); return realApi(path, opts); };   // random delay -> out-of-order responses
  const bad = []; let renders = 0, samples = 0, lastShown = -1, backwards = 0;
  S.onRender = () => { renders++; bad.push(...checkConsistent()); };
  await show();
  play();
  const ticks = Math.round(seconds * 5);
  for (let i = 0; i < ticks; i++) {
    await sleep(200);
    samples++; bad.push(...checkConsistent());
    if (!scrub && S.shownIdx < lastShown) backwards++;
    lastShown = S.shownIdx;
    if (scrub && i > 0 && i % 15 === 0) { S.idx = Math.floor(Math.random() * S.hours.length); $("slider").value = S.idx; S.sliderPending = true; show(); }       // the user drags the slider while playing
  }
  stop();
  await sleep(latency + 800);                                                    // let in-flight requests finish
  bad.push(...checkConsistent());
  // the check itself must be able to fail: corrupt the banner and confirm it is flagged
  const keep = $("simTime").textContent; $("simTime").textContent = "1999-01-01 00:00 IST";
  const caught = checkConsistent().length > 0; $("simTime").textContent = keep;
  const out = { mode: "play", speed, seconds, latency, scrub, renders, samples, requests: S.stats.requests, droppedResponses: S.stats.dropped, popups: S.stats.shown,
                backwardsJumps: backwards, checkerCatchesCorruption: caught, finalSim: S.last && S.last.sim_time_end, violations: bad.slice(0, 8), nViolations: bad.length };
  const pre = document.createElement("pre"); pre.id = "selftest"; pre.hidden = true; pre.style.display = "none"; pre.setAttribute("aria-hidden", "true"); pre.textContent = JSON.stringify(out);
  document.body.appendChild(pre);
}

/* ---------- self test: ?selftest=1&speed=3&steps=80 (used by the developer; steps the player without timers) ---------- */
async function selfTest() {
  const q = new URLSearchParams(location.search);
  const speed = +(q.get("speed") || 3), steps = +(q.get("steps") || 80);
  S.pauseOnAlert = q.get("pauseonalert") === "1";
  const PRF = { healthy: { groups: [], alert_from: 201 }, healthy151: { groups: [], alert_from: 151 }, lung51: { groups: ["lung"], alert_from: 51 } };   // ?profile=
  S.profile = Object.assign({ groups: ["lung"], alert_from: 101, station: S.station }, PRF[q.get("profile")] || {}); renderProfile();
  if (q.get("emailreplay")) $("emailReplay").checked = true;          // test only: also queue the replay e-mails
  const bad = []; let maxToasts = 0, popups = 0, rowsOk = 0, checks = 0, lastIssueKey = "";
  S.idx = Math.max(S.idx - 12, 0);
  const startAt = q.get("start");
  if (startAt) { const k = S.hours.findIndex((h) => h >= startAt); if (k >= 0) S.idx = k; }
  const log = [];
  for (let i = 0; i < steps && S.idx < S.hours.length; i++) {
    const st = await show();
    if (!st) break;
    checks++;
    const rows = $("fcTable").querySelectorAll("tbody tr").length;
    const exr = $("expTable").querySelectorAll("tbody tr").length, cards = $("strip").children.length;
    S.chart.data.datasets.forEach((ds) => { if (!/^(Observed|Your alert)/.test(ds.label)) ds.data.forEach((pt) => { if (pt.x > 24) bad.push("chart point beyond +24 h: " + ds.label + " x=" + pt.x); }); });
    if (S.chart.options.scales.x.max !== 26) bad.push("replay x axis max is " + S.chart.options.scales.x.max + ", expected 26");
    if (rows === 4 && exr === 3 && cards === 4) rowsOk++; else bad.push("rows=" + rows + " experimental=" + exr + " cards=" + cards + " at " + st.sim_time_end);
    const n = $("toasts").children.length; maxToasts = Math.max(maxToasts, n);
    if (n > 1) bad.push("toasts=" + n + " at " + st.sim_time_end);
    const cand = candidate(st);
    if (S.alert && cand && cand.level === "likely" && catRank(cand.f.category) > S.alert.catRank) bad.push("NOT ESCALATED at " + st.sim_time_end + ": alert " + S.alert.aqi + " " + S.alert.category + " but forecast " + cand.f.aqi + " " + cand.f.category);
    if (S.alert && (!log.length || log[log.length - 1].issued !== S.alert.issuedMs)) log.push({ issued: S.alert.issuedMs, at: st.sim_time_end, aqi: S.alert.aqi, cat: S.alert.category, level: S.alert.level, h: S.alert.horizon, title: S.alert.title, warned: S.alert.catRank });
    if (S.alert) {
      const simMs = tms(st.sim_time_end);
      if (S.alert.targetMs <= simMs && !S.alert.stale) bad.push("alert past its target hour is not marked stale at " + st.sim_time_end);
      if (S.alert.level === "possible" && S.alert.horizon > 12) bad.push("possible alert beyond 12 h at " + st.sim_time_end);
      if (S.alert.horizon >= 36) bad.push("pop-up for >= 36 h at " + st.sim_time_end);
      const k = S.alert.station + "|" + S.alert.issuedMs;
      if (k !== lastIssueKey) { popups++; lastIssueKey = k; }
    }
    st.forecasts.forEach((f) => {
      if (f.available) {
        const ex = f.aqi <= 50 ? "Good" : f.aqi <= 100 ? "Satisfactory" : f.aqi <= 200 ? "Moderate" : f.aqi <= 300 ? "Poor" : f.aqi <= 400 ? "Very Poor" : "Severe";
        if (ex !== f.category) bad.push("category " + f.category + " for AQI " + f.aqi);
      }
    });
    S.idx = Math.min(S.idx + speed, S.hours.length - 1);
  }
  const LV = { possible: 1, likely: 2 };
  for (let i = 0; i < log.length; i++) {                                   // label audit: UPDATE labels must match what the PREVIOUS alert warned about
    const cur = log[i], prev = i ? log[i - 1] : null, t = cur.title || "";
    if (/^UPDATE, higher category/.test(t) && !(prev && cur.warned > prev.warned)) bad.push("LABEL 'higher category' without a higher category at " + cur.at + " (" + cur.aqi + " " + cur.cat + "), previous warned rank " + (prev ? prev.warned : "none"));
    if (/^UPDATE, higher alert level/.test(t) && !(prev && cur.warned <= prev.warned && LV[cur.level] > LV[prev.level])) bad.push("LABEL 'higher alert level' wrong at " + cur.at + " (" + cur.aqi + " " + cur.cat + ")");
  }
  const out = { speed, steps, checks, rowsOk, maxToasts, popupsIssued: popups, stats: S.stats, alerts: log.map((x) => x.at + " " + x.level + " " + x.aqi + " " + x.cat + " +" + x.h + "h | " + x.title), violations: bad.slice(0, 10), nViolations: bad.length };
  const pre = document.createElement("pre"); pre.id = "selftest"; pre.hidden = true; pre.style.display = "none"; pre.setAttribute("aria-hidden", "true"); pre.textContent = JSON.stringify(out);
  document.body.appendChild(pre);
}


/* ---------- e-mail (server side; the server recomputes the alert from the saved profile, nothing numeric is trusted from the page) ---------- */
async function postJson(path, body) {
  const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  let j = null; try { j = await r.json(); } catch (e) { /* ignore */ }
  if (!r.ok) { const err = new Error((j && j.detail) ? j.detail : "HTTP " + r.status); err.status = r.status; err.retryAfter = +r.headers.get("Retry-After") || 0; throw err; }
  return j;
}
async function saveServerProfile() {
  const body = { groups: S.profile.groups, station: S.station, alert_from: S.profile.alert_from, email: $("emailAddr").value.trim() };
  const r = await postJson("/api/profile", body);
  $("emailStatus").textContent = "Saved on this computer (groups, station, alert level, e-mail). " +
    (r.email_configured ? "E-mail sending is configured." : "E-mail sending is NOT configured yet (add the three lines to .env).");
  return r;
}
async function sendReplayEmail(escalation, t, period, station) {      // t/period/station are captured WHEN THE ALERT IS RAISED (playback keeps moving)
  try {
    if (!S.account) await saveServerProfile();                         // guest: data/profile.json; logged in: the server uses the account profile
    // the server recomputes the alert for this simulated hour from the saved profile and QUEUES the e-mail; it is sent when the real-time
    // rate limit allows (highest priority first), even if this pop-up has been replaced by then
    const r = await postJson("/api/email/replay-alert", { period, station, t, escalation: escalation || "" });
    $("emailStatus").textContent = r.duplicate ? "No e-mail: " + r.reason : r.queued ? "Replay demo e-mail queued (" + r.pending + " waiting; one is sent per minute at most): " + r.subject
      : "No e-mail: " + (r.reason || "nothing to send");
  } catch (e) { $("emailStatus").textContent = "E-mail not queued: " + e.message; }
}
/* logged in: the settings drawer shows the account profile (edited on the profile page); the replay e-mail switch is stored in the account */
function applyAccountUi() {
  const me = S.account;
  el("guestProfile").hidden = true; el("guestEmail").hidden = true; el("demoProfile").hidden = true;
  const box = el("acctBox"); box.hidden = false; box.innerHTML = accountSummary(me); box.querySelector("b").textContent = me.name;
  const er = el("emailReplay"), es = el("emailStatus");
  er.checked = me.replay_emails;
  const status = () => {
    es.textContent = !me.email_configured ? "E-mail sending is not configured on this computer (.env)."
      : !me.email_verified ? "Replay e-mails go to " + me.email + " once you confirm that address (see your profile page)."
      : me.replay_emails ? "Replay demo alerts are e-mailed to " + me.email + "." : "Tick the box to e-mail replay alerts to " + me.email + ".";
  };
  status();
  er.onchange = async () => {
    try { Object.assign(me, await sendJson("PUT", "/api/me", { replay_emails: er.checked })); status(); }
    catch (e) { es.textContent = "Not saved: " + e.message; er.checked = me.replay_emails; }
  };
}
async function sendJson(method, path, body) {
  const r = await fetch(path, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), credentials: "same-origin" });
  let j = null; try { j = await r.json(); } catch (e) { /* ignore */ }
  if (!r.ok) throw new Error((j && typeof j.detail === "string") ? j.detail : "HTTP " + r.status);
  return j;
}
async function loadServerProfile() {
  try {
    const p = await api("/api/profile");
    if (p.email) $("emailAddr").value = p.email;
    $("emailStatus").textContent = p.email_configured ? "E-mail sending is configured." : "E-mail sending is not configured yet (.env).";
  } catch (e) { /* ignore */ }
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
initServerBar(() => { if (initFailed) location.reload(); });          // red "Server not running" bar; reload once the server is back if start-up failed
init().catch((e) => { initFailed = true; $("adviceBox").textContent = "Could not start: " + e.message; });
