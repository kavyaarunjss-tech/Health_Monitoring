// "Share" (phone share sheet: WhatsApp, Gmail, SMS ...) and "Listen" (phone reads aloud) for the Android Studio app.
// Uses only the advice the backend already gives (sourced); nothing new is written here.
import { fmtClock, pname } from './theme';

const G = () => (typeof globalThis !== 'undefined' ? globalThis : {});
export const shareAvailable = () => !!G().__aqShare;
export const speakAvailable = () => !!G().__aqSpeak;

export function shareText(vm, stationShortName) {
  const n = vm.now;
  const fcs = (vm.forecasts || []).filter((f) => f.available && !f.past && f.horizon <= 24);
  const p = vm.personal || {};
  const top = (p.top3 || [])[0];
  const lines = [
    'Air quality at ' + vm.stationName + (vm.mode === 'replay' ? ' (replay demo, past data)' : ''),
    n ? 'Now: AQI ' + n.aqi + ' (' + n.category + ')' + (n.dominant ? ', mainly ' + pname(n.dominant) : '') : 'Now: no valid AQI',
    fcs.length ? 'Next 24 h forecast: ' + fcs.map((f) => '+' + f.horizon + ' h ' + f.aqi + ' (' + f.category + ')').join(', ') : null,
    top ? 'Tip: ' + top.text + (top.source ? ' ' + top.source : '') : null,
    'Official CPCB AQI · AQ Health app · not medical advice',
  ];
  return { subject: 'Air quality at ' + (stationShortName || vm.stationName), text: lines.filter(Boolean).join('\n') };
}

export function share(vm, stationShortName) {
  const t = shareText(vm, stationShortName);
  if (G().__aqShare) G().__aqShare(t.subject, t.text);
}

// text for the voice: no source numbers, pollutant names spelled out
function speakable(s) {
  return String(s || '')
    .replace(/\[\d+\]/g, '')
    .replace(/\(our forecast\)/g, '')
    .replace(/\*\*/g, '')
    .replace(/PM2\.5/g, 'P M 2 point 5')
    .replace(/PM10/g, 'P M 10')
    .replace(/NO₂/g, 'nitrogen dioxide')
    .replace(/SO₂/g, 'sulphur dioxide')
    .replace(/O₃/g, 'ozone')
    .replace(/\bAQI\b/g, 'A Q I')
    .replace(/(\d+)–(\d+)/g, '$1 to $2')
    .replace(/\s+/g, ' ')
    .trim();
}

export function speakSummary(vm) {
  const n = vm.now;
  const p = vm.personal || {};
  const fcs = (vm.forecasts || []).filter((f) => f.available && !f.past && f.horizon <= 24);
  const max = fcs.reduce((m, f) => (!m || f.aqi > m.aqi ? f : m), null);
  const parts = [
    'Air quality at ' + vm.stationName + '.',
    n ? 'Right now the AQI is ' + n.aqi + ', ' + n.category + '.' : 'There is no valid AQI right now.',
    max ? 'In the next 24 hours it may reach ' + max.aqi + ', ' + max.category + ', around ' + fmtClock(max.target_end, vm.clock) + '.' : '',
    ...(p.top3 || []).map((x) => x.text + '.'),
    'This is general guidance, not medical advice.',
  ];
  return say(parts.join(' '));
}

export function speakAlert(a) {
  const f = a.f;
  const likely = a.level === 'likely';
  const parts = [
    'Air quality alert for ' + a.stationName + '.',
    likely
      ? f.category + ' air is likely around ' + fmtClock(f.target_end, a.issued) + ', with an A Q I of about ' + f.aqi + '.'
      : 'The A Q I could reach ' + f.range_high + ', ' + f.category_high + ', around ' + fmtClock(f.target_end, a.issued) + '.',
    ...(a.actions || []).slice(0, 2).map((x) => x.text + '.'),
    'Not medical advice. In an emergency call 1 1 2.',
  ];
  return say(parts.join(' '));
}

export function say(text) {
  return G().__aqSpeak ? G().__aqSpeak(speakable(text)) : false;
}
export function stopSpeaking() {
  if (G().__aqStopSpeak) G().__aqStopSpeak();
}
