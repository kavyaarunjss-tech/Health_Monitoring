// Colours, names and small helpers shared by every screen.
// CPCB category colours and text colours are the same as the website (frontend/style.css), chosen for WCAG AA contrast.

export const C = {
  bg: '#0b1320',
  card: '#131c2b',
  card2: '#1c2738',
  nav: '#0f1826',
  text: '#f2f5f9',
  soft: '#b9c4d0',
  muted: '#9aa8b8',
  faint: '#8593a3',
  accent: '#7cc4ff',
  selBg: '#16233a',
  selBorder: '#3b6a9a',
  good: '#5fd08a',
  warnBg: '#2a1b0e',
  warnText: '#ffd9bd',
  warnIcon: '#ffb27a',
  dangerBg: '#2b1215',
  danger: '#ff8a8f',
  infoBg: '#10263a',
};

// CPCB category colours, brightened slightly so they stay clear on the dark background
export const CAT = {
  Good: { bg: '#3fbf6f', fg: '#08130c' },
  Satisfactory: { bg: '#a8d64a', fg: '#11180a' },
  Moderate: { bg: '#f5c400', fg: '#1a1500' },
  Poor: { bg: '#ff8a2a', fg: '#1f1000' },
  'Very Poor': { bg: '#e5484d', fg: '#ffffff' },
  Severe: { bg: '#a3262a', fg: '#ffffff' },
};
export const CAT_ORDER = ['Good', 'Satisfactory', 'Moderate', 'Poor', 'Very Poor', 'Severe'];
export const catStyle = (c) => CAT[c] || { bg: '#4a5668', fg: '#f2f5f9' };
export const catRank = (c) => CAT_ORDER.indexOf(c);

export const PNAME = { pm25: 'PM2.5', pm10: 'PM10', no2: 'NO₂', so2: 'SO₂', o3: 'O₃', co: 'CO' };
export const pname = (k) => PNAME[k] || k || '';

export const STATIONS = [
  { id: 'silkboard', name: 'Silk Board, Bengaluru', short: 'Silk Board' },
  { id: 'hebbal', name: 'Hebbal, Bengaluru', short: 'Hebbal' },
  { id: 'jayanagar', name: 'Jayanagar 5th Block, Bengaluru', short: 'Jayanagar' },
  { id: 'chikkaballapura', name: 'Chikkaballapur Rural', short: 'Chikkaballapur' },
  { id: 'chikkamagaluru', name: 'Kalyana Nagara, Chikkamagaluru', short: 'Chikkamagaluru' },
  { id: 'mysuru', name: 'Hebbal 1st Stage, Mysuru', short: 'Mysuru' },
  { id: 'ramanagara', name: 'Vijay Nagar, Ramanagara', short: 'Ramanagara' },
  { id: 'madikeri', name: 'Stuart Hill, Madikeri', short: 'Madikeri' },
];
export const stationName = (id) => (STATIONS.find((s) => s.id === id) || {}).name || id;
export const stationShort = (id) => (STATIONS.find((s) => s.id === id) || {}).short || id;

// health groups (same keys as the backend, advice.py)
export const GROUPS = [
  { id: 'lung', label: 'Lung disease (asthma, COPD)' },
  { id: 'heart', label: 'Heart disease' },
  { id: 'child', label: 'Child (under 14)' },
  { id: 'older', label: 'Older adult (60+)' },
  { id: 'pregnant', label: 'Pregnant' },
  { id: 'outdoor_worker', label: 'Outdoor worker' },
  { id: 'athlete', label: 'Exercise outdoors regularly' },
];

// Alert levels: same rule as the backend (advice.thresholds). Vulnerable groups 101, healthy adults 201, everyone 301.
// A user may LOWER the level, never raise it.
export function defaultAlert(groups) {
  return groups && groups.length ? 101 : 201;
}
export function alertLevel(profile) {
  const d = defaultAlert(profile && profile.groups);
  const o = profile && profile.alertOverride;
  return Math.min(o && o < d ? o : d, 301);
}
export const ALERT_CHOICES = [51, 101, 151, 201];

// ---- time helpers. Backend times are IST wall-clock strings; we treat them as UTC numbers so no phone time zone interferes.
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
export function toMs(s) {
  if (!s) return NaN;
  const m = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/.exec(s);
  if (!m) return NaN;
  return Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5]);
}
const p2 = (n) => (n < 10 ? '0' + n : '' + n);
export function labelFromMs(ms) {
  const d = new Date(ms);
  return `${d.getUTCFullYear()}-${p2(d.getUTCMonth() + 1)}-${p2(d.getUTCDate())} ${p2(d.getUTCHours())}:${p2(d.getUTCMinutes())}:00`;
}
export function fmtTime(s) {
  const ms = toMs(s);
  if (isNaN(ms)) return s || '';
  const d = new Date(ms);
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}, ${p2(d.getUTCHours())}:${p2(d.getUTCMinutes())}`;
}
export function fmtHour(s) {
  const ms = toMs(s);
  if (isNaN(ms)) return s || '';
  const d = new Date(ms);
  return `${p2(d.getUTCHours())}:${p2(d.getUTCMinutes())}`;
}
export const HOUR = 3600 * 1000;

// CPCB category of a displayed (rounded) AQI value
export function catOf(aqi) {
  if (aqi == null || isNaN(aqi)) return null;
  const a = Math.round(aqi);
  if (a <= 50) return 'Good';
  if (a <= 100) return 'Satisfactory';
  if (a <= 200) return 'Moderate';
  if (a <= 300) return 'Poor';
  if (a <= 400) return 'Very Poor';
  return 'Severe';
}

// position (0..1) of an AQI value on the CPCB scale bar whose segments are 0-50, 50-100 (narrow) and 100-200 ... 400-500 (wide)
export function scalePos(aqi) {
  const a = Math.max(0, Math.min(500, aqi || 0));
  if (a <= 100) return (a / 100) * 0.2;
  return 0.2 + ((a - 100) / 400) * 0.8;
}

// "3 AM", or "Sat 3 AM" when the day differs from the reference time
const WD = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
export function fmtClock(s, ref) {
  const ms = toMs(s);
  if (isNaN(ms)) return s || '';
  const d = new Date(ms);
  let h = d.getUTCHours();
  const ap = h < 12 ? 'AM' : 'PM';
  h = h % 12 || 12;
  const t = h + ' ' + ap;
  if (ref) {
    const r = new Date(toMs(ref));
    if (r.getUTCDate() !== d.getUTCDate()) return WD[d.getUTCDay()] + ' ' + t;
  }
  return t;
}
export function fmtDay(s) {
  const ms = toMs(s);
  if (isNaN(ms)) return s || '';
  const d = new Date(ms);
  return WD[d.getUTCDay()] + ' ' + d.getUTCDate() + ' ' + MONTHS[d.getUTCMonth()];
}
