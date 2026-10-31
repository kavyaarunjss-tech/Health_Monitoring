// E-mail alerts and health summaries, sent by the phone itself through Gmail.
// Only the Android Studio app can send (it has the native mail sender, MailSender.java); in Expo Go mailAvailable() is false.
// All health wording comes from the backend's advice (sourced from docs/health_advisory_reference.md); nothing new is invented here.
import { fmtTime, fmtDay, fmtClock, pname, catRank, stationShort, GROUPS } from './theme';

const M = () => (typeof globalThis !== 'undefined' && globalThis.__aqMail) || null;

export const mailAvailable = () => !!M();
export function mailStatus() {
  const m = M();
  return m ? m.status() : { configured: false, sender: '' };
}
export function saveSender(user, pass) {
  const m = M();
  return m ? m.save(user, pass) : 'E-mail works only in the Android Studio app.';
}
export function clearSender() {
  const m = M();
  if (m) m.clear();
}
export const validEmail = (s) => /^[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+$/.test(String(s || '').trim());

export async function sendMail(to, mail) {
  const m = M();
  if (!m) return { ok: false, message: 'E-mail works only in the Android Studio app.' };
  if (!mailStatus().configured) return { ok: false, message: 'Set up the sending Gmail account first (Profile → E-mail alerts).' };
  if (!validEmail(to)) return { ok: false, message: 'Enter your e-mail address first (Profile → E-mail alerts).' };
  try {
    return await m.send(String(to).trim(), mail.subject, mail.text, mail.html);
  } catch (e) {
    return { ok: false, message: 'Could not send the e-mail.' };
  }
}

// ---------------------------------------------------------------- alert outbox
// At most one e-mail per 60 s (fast replay can raise several alerts in a minute). While waiting, only the most important
// pending alert is kept (escalation, then higher category, then likely over possible, then higher AQI; newest wins a tie).
// The same alert (station + issue hour + level) is never e-mailed twice, even after a rewind or a restart.
const GAP_MS = 60 * 1000;
const SENT_KEY = 'aqhealth.mailsent.v1';
let lastSendAt = 0;
let pending = null;
let timer = null;
let busy = false;

function sentKeys() {
  try {
    return JSON.parse(globalThis.localStorage.getItem(SENT_KEY) || '[]');
  } catch (e) {
    return [];
  }
}
function remember(key) {
  try {
    const k = sentKeys().filter((x) => x !== key);
    k.push(key);
    globalThis.localStorage.setItem(SENT_KEY, JSON.stringify(k.slice(-300)));
  } catch (e) {
    // storage unavailable: duplicates are then only prevented within this session
  }
}
const priority = (it) => [it.escalation ? 1 : 0, it.rank, it.level === 'likely' ? 1 : 0, it.aqi];
function higherOrEqual(a, b) {
  const x = priority(a);
  const y = priority(b);
  for (let i = 0; i < x.length; i++) if (x[i] !== y[i]) return x[i] > y[i];
  return true;
}

/** item = { key, to, mail, rank, level, aqi, escalation }; onResult(result, item) is called after each send. */
export function queueAlertMail(item, onResult) {
  if (sentKeys().includes(item.key)) return 'duplicate';
  if (pending && pending.key === item.key) return 'queued';
  if (pending && !higherOrEqual(item, pending)) return 'lower';
  pending = { ...item, onResult };
  pump();
  return 'queued';
}

function pump() {
  if (busy || !pending) return;
  const wait = lastSendAt + GAP_MS - Date.now();
  if (wait > 0) {
    if (!timer) timer = setTimeout(() => { timer = null; pump(); }, wait + 50);
    return;
  }
  const it = pending;
  pending = null;
  busy = true;
  lastSendAt = Date.now();
  remember(it.key); // claimed before sending: a rewind during the send cannot repeat it
  sendMail(it.to, it.mail).then((r) => {
    busy = false;
    if (it.onResult) it.onResult(r, it);
    pump();
  });
}

// ---------------------------------------------------------------- composing
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const bold = (s) => esc(s).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>');
const CAT_BG = { Good: '#3fbf6f', Satisfactory: '#a8d64a', Moderate: '#f5c400', Poor: '#ff8a2a', 'Very Poor': '#d6363c', Severe: '#a3262a' };
const CAT_FG = { 'Very Poor': '#ffffff', Severe: '#ffffff' };
const pill = (cat, txt) =>
  '<span style="display:inline-block;padding:2px 10px;border-radius:12px;font-weight:700;background:' + (CAT_BG[cat] || '#9aa8b8') +
  ';color:' + (CAT_FG[cat] || '#111111') + '">' + esc(txt || cat) + '</span>';
const groupsText = (groups) =>
  groups && groups.length ? groups.map((g) => (GROUPS.find((x) => x.id === g) || { label: g }).label).join(', ') : 'healthy adult';
const srcs = (s) => (s ? ' ' + s : '');

function refsUsed(texts, meta) {
  const refs = (meta && meta.references) || {};
  const used = new Set();
  texts.forEach((t) => String(t || '').replace(/\[(\d+)\]/g, (_, n) => used.add(n)));
  return [...used].sort((a, b) => a - b).filter((n) => refs[n]).map((n) => '[' + n + '] ' + refs[n]);
}
const DISCLAIMER_SHORT = 'General information from public health guidance (CPCB, Ministry of Health and Family Welfare, WHO), not medical advice. Forecasts come from a statistical model and can be wrong. In an emergency call 112.';

function wrapHtml(title, inner, footer) {
  return (
    '<!doctype html><html><body style="margin:0;background:#f4f6f9;font-family:Arial,Helvetica,sans-serif;color:#1b2330">' +
    '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f6f9"><tr><td align="center" style="padding:16px">' +
    '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;background:#ffffff;border-radius:12px">' +
    '<tr><td style="background:#0b1320;color:#ffffff;padding:16px 20px;border-radius:12px 12px 0 0;font-size:13px;letter-spacing:1px;font-weight:700">AQ HEALTH · ' + esc(title) + '</td></tr>' +
    '<tr><td style="padding:20px;font-size:15px;line-height:1.5">' + inner + '</td></tr>' +
    '<tr><td style="padding:14px 20px;color:#5b6675;font-size:12px;line-height:1.5;border-top:1px solid #e3e7ed">' + footer + '</td></tr>' +
    '</table></td></tr></table></body></html>'
  );
}
const li = (items) => '<ul style="padding-left:20px;margin:6px 0 14px">' + items.map((x) => '<li style="margin:4px 0">' + x + '</li>').join('') + '</ul>';
const h3 = (t) => '<div style="font-weight:700;font-size:16px;margin:16px 0 4px">' + esc(t) + '</div>';

/** E-mail for an alert raised by the app (a = the alert object built in App.js). */
export function composeAlert(a, profile, meta, replay) {
  const f = a.f;
  const likely = a.level === 'likely';
  const cat = likely ? f.category : f.category_high;
  const station = a.stationName;
  const when = fmtTime(f.target_end);
  const tag = replay ? '[REPLAY DEMO] ' : '';
  const upd = a.escalation ? 'UPDATE, ' + a.escalation + ': ' : '';
  const subject =
    tag + upd + (likely ? cat + ' air likely' : cat + ' air possible') + ' at ' + stationShort(profile.station) +
    ' · AQI ' + (likely ? f.aqi : f.range_high) + ' for ' + fmtClock(f.target_end, a.issued);
  const name = profile.name ? profile.name.trim() : '';
  const forecastLine = likely
    ? 'Forecast AQI ' + f.aqi + ' (' + f.category + '), likely range ' + f.range_low + '–' + f.range_high
    : 'Forecast AQI ' + f.aqi + ' (' + f.category + '), could reach ' + f.range_high + ' (' + f.category_high + ')';
  const p = a.personal || {};
  const actions = (a.actions || []).map((x) => x.text + srcs(x.source));
  const actionsHtml = (a.actions || []).map((x) => bold(x.marked || x.text) + esc(srcs(x.source)));
  const covered = new Set((a.actions || []).flatMap((x) => x.covers || [x.text]));
  const more = (p.full || []).filter((x) => x.kind !== 'headline' && !covered.has(x.text));
  const head = p.headline ? p.headline.text + srcs(p.headline.source) : '';
  const demo = replay
    ? 'This is a SIMULATED alert from the AQ Health replay demo: the app is replaying real past data (' + fmtDay(a.issued) + '), not today\'s air.'
    : '';

  const text = [
    (name ? 'Hello ' + name + ',' : 'Hello,'),
    '',
    demo,
    demo ? '' : null,
    (likely ? 'AIR QUALITY ALERT' : 'POSSIBLE AIR QUALITY ALERT') + (a.escalation ? ' (UPDATE, ' + a.escalation + ')' : ''),
    'Station: ' + station,
    forecastLine + ' for the hour ending ' + when + ' (+' + f.horizon + ' h forecast).',
    f.dominant ? 'Main pollutant: ' + pname(f.dominant) : null,
    'Issued: hour ending ' + fmtTime(a.issued) + (replay ? ' (replay time)' : ''),
    'Your alert level: AQI ' + a.alertFrom + ' (profile: ' + groupsText(profile.groups) + ')',
    '',
    head ? 'What this level means: ' + head : null,
    '',
    'What you can do now:',
    ...actions.map((x) => '- ' + x),
    more.length ? '' : null,
    more.length ? 'More advice for you:' : null,
    ...more.map((x) => '- ' + x.text + srcs(x.source)),
    '',
    'Sources:',
    ...refsUsed([head, ...actions, ...more.map((x) => x.source)], meta),
    '',
    (meta && meta.disclaimer) || DISCLAIMER_SHORT,
    '',
    'You get this e-mail because e-mail alerts are on in the AQ Health app (Profile → E-mail alerts). At most one alert per station every 12 hours, unless it gets worse.',
  ]
    .filter((x) => x !== null)
    .join('\n')
    .replace(/\n{3,}/g, '\n\n');

  const inner =
    (demo ? '<div style="background:#fff4e5;border-left:4px solid #ff8a2a;padding:10px 12px;margin-bottom:14px;font-size:14px">' + esc(demo) + '</div>' : '') +
    '<div style="font-size:13px;color:#5b6675;font-weight:700;letter-spacing:.5px">' + (likely ? 'AIR QUALITY ALERT' : 'POSSIBLE AIR QUALITY ALERT') +
    (a.escalation ? ' · UPDATE, ' + esc(a.escalation).toUpperCase() : '') + '</div>' +
    '<div style="font-size:24px;font-weight:700;margin:6px 0 4px">' + esc(cat) + ' air ' + (likely ? 'likely' : 'possible') + ' at ' + esc(station) + '</div>' +
    '<div style="margin:8px 0 12px">' + pill(f.category, 'AQI ' + f.aqi + ' · ' + f.category) +
    (likely ? ' <span style="color:#5b6675">likely ' + f.range_low + '–' + f.range_high + '</span>' : ' <span style="color:#5b6675">could reach ' + f.range_high + ' (' + esc(f.category_high) + ')</span>') + '</div>' +
    '<table role="presentation" cellpadding="0" cellspacing="0" style="font-size:14px;margin-bottom:6px">' +
    [['For', 'the hour ending ' + when + ' (+' + f.horizon + ' h forecast)'], f.dominant ? ['Main pollutant', pname(f.dominant)] : null,
      ['Issued', 'hour ending ' + fmtTime(a.issued) + (replay ? ' (replay time)' : '')], ['Your alert level', 'AQI ' + a.alertFrom + ' · ' + groupsText(profile.groups)]]
      .filter(Boolean)
      .map((r) => '<tr><td style="color:#5b6675;padding:2px 14px 2px 0">' + esc(r[0]) + '</td><td>' + esc(r[1]) + '</td></tr>')
      .join('') +
    '</table>' +
    (head ? h3('What this level means') + '<div>' + esc(head) + '</div>' : '') +
    h3('What you can do now') + li(actionsHtml) +
    (more.length ? h3('More advice for you') + li(more.map((x) => bold(x.marked || x.text) + esc(srcs(x.source)))) : '');
  const footer =
    '<b>Sources:</b><br>' + refsUsed([head, ...actions, ...more.map((x) => x.source)], meta).map(esc).join('<br>') + '<br><br>' +
    esc((meta && meta.disclaimer) || DISCLAIMER_SHORT) + '<br><br>You get this e-mail because e-mail alerts are on in the AQ Health app (Profile → E-mail alerts).';
  return { subject, text, html: wrapHtml(likely ? 'AIR QUALITY ALERT' : 'POSSIBLE ALERT', inner, footer) };
}

/** "Health summary now": current air, the next 24 h, personal advice and this week's summary. */
export function composeSummary(vm, week, profile, meta, alertFrom) {
  const station = vm.stationName;
  const replay = vm.mode === 'replay';
  const tag = replay ? '[REPLAY DEMO] ' : '';
  const name = profile.name ? profile.name.trim() : '';
  const now = vm.now;
  const subject = tag + 'Your air and health summary · ' + stationShort(profile.station) + (now ? ' · AQI ' + now.aqi + ' (' + now.category + ')' : '');
  const p = vm.personal || {};
  const fcs = (vm.forecasts || []).filter((f) => f.available && f.horizon <= 24);
  const actions = (p.top3 || []).map((x) => x.text + srcs(x.source));
  const head = p.headline ? p.headline.text + srcs(p.headline.source) : '';
  const trend = p.trend ? p.trend.text + srcs(p.trend.source) : '';
  const wk = week && week.enough ? week : null;
  const wkActions = wk ? ((wk.health && wk.health.actions) || []).filter((x) => (wk.top3 || []).includes(x.id)) : [];
  const wkText = wk
    ? (() => {
        const valid = (wk.days || []).filter((d) => d.valid);
        const bad = valid.filter((d) => catRank(d.category) >= 2).length;
        const dir = (wk.trend || {}).direction;
        return [
          'Days: ' + (wk.days || []).map((d) => d.weekday + ' ' + (d.valid ? d.category + ' (' + d.aqi + ')' : 'no data')).join(', '),
          bad + ' of 7 days Moderate or worse; trend: ' + (dir === 'rising' ? 'getting worse' : dir === 'falling' ? 'getting better' : 'steady') +
            (wk.dominant ? '; main pollutant: ' + pname(wk.dominant) : ''),
        ];
      })()
    : ['Not enough data for a weekly summary (needs at least 5 of 7 days).'];
  const when = replay ? 'Replay time: hour ending ' + fmtTime(vm.clock) : vm.timeLine;
  const demo = replay ? 'This summary comes from the AQ Health replay demo (real past data, ' + fmtDay(vm.clock) + '), not today\'s air.' : '';
  const sourcesList = refsUsed([head, trend, ...actions, ...wkActions.map((x) => (x.sources || []).map((n) => '[' + n + ']').join(''))], meta);

  const text = [
    name ? 'Hello ' + name + ',' : 'Hello,',
    '',
    demo,
    demo ? '' : null,
    'AIR AND HEALTH SUMMARY · ' + station,
    when,
    'Profile: ' + groupsText(profile.groups) + ' · alert level AQI ' + alertFrom,
    '',
    now ? 'Now: AQI ' + now.aqi + ' (' + now.category + ')' + (now.dominant ? ', mainly ' + pname(now.dominant) : '') : 'Now: no valid AQI for this hour.',
    head ? (p.aqi != null && now && p.aqi !== now.aqi ? 'Advice is for AQI ' + p.aqi + ', the highest of now and the next 24 h: ' : '') + head : null,
    '',
    'Next 24 hours (our forecast):',
    ...(fcs.length ? fcs.map((f) => '- +' + f.horizon + ' h (hour ending ' + fmtTime(f.target_end) + '): AQI ' + f.aqi + ' (' + f.category + '), likely ' + f.range_low + '–' + f.range_high) : ['- no forecast available for these hours']),
    trend ? trend : null,
    '',
    'Your top actions:',
    ...(actions.length ? actions.map((x) => '- ' + x) : ['- No special precautions needed for your profile at this level.']),
    '',
    'This week (7 days):',
    ...wkText,
    ...wkActions.map((x) => '- ' + x.text + ' ' + (x.sources || []).map((n) => '[' + n + ']').join('')),
    '',
    'Sources:',
    ...sourcesList,
    '',
    (meta && meta.disclaimer) || DISCLAIMER_SHORT,
  ]
    .filter((x) => x !== null)
    .join('\n')
    .replace(/\n{3,}/g, '\n\n');

  const fcRows = fcs
    .map((f) => '<tr><td style="padding:6px 10px 6px 0">+' + f.horizon + ' h<br><span style="color:#5b6675;font-size:12px">' + esc(fmtTime(f.target_end)) + '</span></td><td style="padding:6px 0">' +
      pill(f.category, f.aqi + ' · ' + f.category) + ' <span style="color:#5b6675;font-size:13px">likely ' + f.range_low + '–' + f.range_high + '</span></td></tr>')
    .join('');
  const dots = wk
    ? '<div style="margin:6px 0">' + (wk.days || []).map((d) =>
        '<span style="display:inline-block;text-align:center;margin:0 6px 6px 0;font-size:12px;color:#5b6675"><span style="display:block;width:26px;height:26px;border-radius:13px;margin:0 auto 2px;background:' +
        (d.valid ? CAT_BG[d.category] || '#9aa8b8' : '#d7dce3') + '"></span>' + esc(d.weekday) + '</span>').join('') + '</div>'
    : '';
  const inner =
    (demo ? '<div style="background:#fff4e5;border-left:4px solid #ff8a2a;padding:10px 12px;margin-bottom:14px;font-size:14px">' + esc(demo) + '</div>' : '') +
    '<div style="font-size:13px;color:#5b6675">' + esc(when) + ' · ' + esc(groupsText(profile.groups)) + '</div>' +
    '<div style="font-size:22px;font-weight:700;margin:6px 0">' + esc(station) + '</div>' +
    (now ? '<div style="margin:6px 0 4px">' + pill(now.category, 'AQI ' + now.aqi + ' · ' + now.category) + (now.dominant ? ' <span style="color:#5b6675">mainly ' + esc(pname(now.dominant)) + '</span>' : '') + '</div>' : '<div>No valid AQI for this hour.</div>') +
    (head ? '<div style="margin:8px 0">' + (p.aqi != null && now && p.aqi !== now.aqi ? '<span style="color:#5b6675">Advice is for AQI ' + p.aqi + ', the highest of now and the next 24 h: </span>' : '') + esc(head) + '</div>' : '') +
    h3('Next 24 hours (our forecast)') +
    (fcRows ? '<table role="presentation" cellpadding="0" cellspacing="0" style="font-size:14px">' + fcRows + '</table>' : '<div>No forecast available for these hours.</div>') +
    (trend ? '<div style="margin-top:6px;color:#5b6675;font-size:14px">' + esc(trend) + '</div>' : '') +
    h3('Your top actions') +
    li(actions.length ? (p.top3 || []).map((x) => bold(x.marked || x.text) + esc(srcs(x.source))) : ['No special precautions needed for your profile at this level.']) +
    h3('This week') + dots + li(wkText.slice(wk ? 1 : 0).map(esc).concat(wkActions.map((x) => bold(x.marked || x.text) + ' ' + esc((x.sources || []).map((n) => '[' + n + ']').join('')))));
  const footer = '<b>Sources:</b><br>' + sourcesList.map(esc).join('<br>') + '<br><br>' + esc((meta && meta.disclaimer) || DISCLAIMER_SHORT);
  return { subject, text, html: wrapHtml('HEALTH SUMMARY', inner, footer) };
}

export function composeTest(profile, sender) {
  const subject = 'AQ Health: test e-mail';
  const text =
    (profile.name ? 'Hello ' + profile.name.trim() + ',' : 'Hello,') +
    '\n\nE-mail alerts from the AQ Health app are working. Air quality alerts and health summaries will arrive at this address, sent from ' +
    sender + '.\n\n' + DISCLAIMER_SHORT;
  const html = wrapHtml('TEST E-MAIL', '<div style="font-size:20px;font-weight:700;margin-bottom:8px">E-mail alerts are working ✓</div><div>Air quality alerts and health summaries will arrive at this address, sent from ' + esc(sender) + '.</div>', esc(DISCLAIMER_SHORT));
  return { subject, text, html };
}

