// Colours, names and small helpers shared by every screen.
// CPCB category colours and text colours are the same as the website (frontend/style.css), chosen for WCAG AA contrast.

export const C = {
  navy: '#0b3c5d',
  teal: '#0f6e78',
  bg: '#f4f6f9',
  card: '#ffffff',
  text: '#0f1d2b',
  muted: '#5b6b7b',
  border: '#e2e8f0',
  danger: '#c62828',
  warnBg: '#fff4e5',
  warnText: '#8a4b00',
  infoBg: '#e8f3f5',
};

export const CAT = {
  Good: { bg: '#1a7f3c', fg: '#ffffff' },
  Satisfactory: { bg: '#9ccc3c', fg: '#0f1d2b' },
  Moderate: { bg: '#f5c400', fg: '#0f1d2b' },
  Poor: { bg: '#ef7d0f', fg: '#0f1d2b' },
  'Very Poor': { bg: '#c62828', fg: '#ffffff' },
  Severe: { bg: '#7a1212', fg: '#ffffff' },
};
export const CAT_ORDER = ['Good', 'Satisfactory', 'Moderate', 'Poor', 'Very Poor', 'Severe'];
export const catStyle = (c) => CAT[c] || { bg: '#9aa5b1', fg: '#ffffff' };
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
