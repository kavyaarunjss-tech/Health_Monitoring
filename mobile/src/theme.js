// Design system: colour tokens, type, radii, shadows and the theme engine (Light / Dark / System).
// Soft wellness look: white cards on a soft white page with blurred colour glows; near-black layers with dimmed glows in dark mode.
// CPCB category colours are the only strong colours; every text/background pair here was checked for WCAG AA (4.5:1).
import { Appearance } from 'react-native';

const LIGHT = {
  bg: '#f6f7f9', // soft white page
  bg2: '#f1f2f5',
  card: '#ffffff', // floating white cards
  card2: '#f1f2f5', // inset surface (chips, tracks)
  line: '#e9eaee',
  nav: '#ffffff',
  text: '#15161a',
  soft: '#3f434b',
  muted: '#626773',
  faint: '#686d78',
  accent: '#5a4bd1', // soft indigo: links and active states
  accentBg: '#eeecff',
  selBg: '#eeecff',
  selBorder: '#b9b1f2',
  good: '#1f7a47',
  warnBg: '#fff0e5',
  warnText: '#7a3410',
  warnIcon: '#a8501c',
  dangerBg: '#fde8e8',
  danger: '#a8282d',
  dangerText: '#8a1c1c',
  infoBg: '#e7f0ff',
  infoText: '#1e427a',
  strong: '#15161a',
  onPrimary: '#ffffff',
  primary: '#15161a',
  shadow: '#1b1d2b',
  // pastel tints (backgrounds only; text on them uses the matching *Text)
  sage: '#e5f5ec',
  lavender: '#eeecff',
  peach: '#ffede2',
  butter: '#fff5d9',
  sky: '#e7f0ff',
  sageText: '#1f5a3a',
  lavenderText: '#3b3285',
  peachText: '#7a3a12',
  butterText: '#5e4a08',
  skyText: '#1e427a',
  glowA: 'rgba(255,168,118,0.42)', // soft peach light
  glowB: 'rgba(160,148,255,0.34)', // soft lavender light
};
const DARK = {
  bg: '#0e0f12', // near-black
  bg2: '#121317',
  card: '#17181d', // layered surfaces
  card2: '#202228',
  line: '#2a2c33',
  nav: '#17181d',
  text: '#f3f4f6',
  soft: '#cdd0d6',
  muted: '#9a9fa8',
  faint: '#8e939c',
  accent: '#a99cff',
  accentBg: '#1f1d33',
  selBg: '#1f1d33',
  selBorder: '#5b52a8',
  good: '#8fd9ae',
  warnBg: '#2b1e15',
  warnText: '#f7cbae',
  warnIcon: '#f2a874',
  dangerBg: '#2c1718',
  danger: '#f08a8c',
  dangerText: '#f5bdbd',
  infoBg: '#16202f',
  infoText: '#c3d6f5',
  strong: '#ffffff',
  onPrimary: '#111216',
  primary: '#f3f4f6',
  shadow: '#000000',
  sage: '#15241c',
  lavender: '#1f1d33',
  peach: '#2a1d16',
  butter: '#262213',
  sky: '#16202f',
  sageText: '#b9e6cb',
  lavenderText: '#d3ccff',
  peachText: '#f7c9ae',
  butterText: '#f0dd9c',
  skyText: '#c3d6f5',
  glowA: 'rgba(255,150,100,0.20)',
  glowB: 'rgba(140,120,255,0.20)',
};

// ---------------------------------------------------------------- theme engine
// The choice ("light", "dark" or "system") is saved on the phone. "system" follows the phone's dark-mode setting and
// switches when it changes. The screens are built from these tokens once, so a change reloads the app (under a second,
// built-in data); the replay starts again from its first event.
const MODE_KEY = 'aqhealth.theme';
const G = typeof globalThis !== 'undefined' ? globalThis : {};
function readMode() {
  try {
    const v = G.localStorage && G.localStorage.getItem(MODE_KEY);
    return v === 'light' || v === 'dark' || v === 'system' ? v : 'system';
  } catch (e) {
    return 'system';
  }
}
export function systemPrefersDark() {
  try {
    if (G.AQAndroid && G.AQAndroid.systemDark) return !!G.AQAndroid.systemDark();
  } catch (e) {
    // fall through
  }
  try {
    if (G.matchMedia) return G.matchMedia('(prefers-color-scheme: dark)').matches;
  } catch (e) {
    // fall through
  }
  try {
    return Appearance && Appearance.getColorScheme && Appearance.getColorScheme() === 'dark';
  } catch (e) {
    return false;
  }
}
export const THEME_MODE = readMode();
export const THEME = THEME_MODE === 'system' ? (systemPrefersDark() ? 'dark' : 'light') : THEME_MODE;
export const C = THEME === 'light' ? LIGHT : DARK;
export const themeSwitchAvailable = () => {
  try {
    return !!(G.localStorage && G.location && G.location.reload);
  } catch (e) {
    return false;
  }
};
export function setThemeMode(mode) {
  const m = mode === 'light' || mode === 'dark' ? mode : 'system';
  try {
    G.localStorage.setItem(MODE_KEY, m);
    if (G.AQAndroid && G.AQAndroid.saveTheme) G.AQAndroid.saveTheme(m);
    G.location.reload();
  } catch (e) {
    // not available (Expo Go): the app keeps following the phone's setting
  }
}
export const setTheme = setThemeMode; // older name
// "system": reload when the phone switches between light and dark
G.__aqSystemThemeChanged = function () {
  if (THEME_MODE !== 'system') return;
  const want = systemPrefersDark() ? 'dark' : 'light';
  if (want !== THEME) {
    try {
      G.location.reload();
    } catch (e) {
      // ignore
    }
  }
};
try {
  if (G.matchMedia && !(G.AQAndroid && G.AQAndroid.systemDark)) {
    const mq = G.matchMedia('(prefers-color-scheme: dark)');
    if (mq.addEventListener) mq.addEventListener('change', () => G.__aqSystemThemeChanged());
  }
} catch (e) {
  // ignore
}
// page background, scrollbars and Android status/navigation bars follow the theme
try {
  if (G.document && G.document.documentElement) {
    const st = G.document.documentElement.style;
    st.colorScheme = THEME;
    st.background = C.bg;
    G.document.documentElement.setAttribute('data-theme', THEME);
    if (G.document.body) G.document.body.style.background = C.bg;
    const r = G.document.getElementById && G.document.getElementById('root');
    if (r) {
      r.style.background = C.bg;
      r.style.color = C.text;
    }
  }
  if (G.AQAndroid && G.AQAndroid.setSystemBars) G.AQAndroid.setSystemBars(C.bg, THEME === 'light');
} catch (e) {
  // not a web page
}

// ---------------------------------------------------------------- type, shape, depth
const WEB = typeof document !== 'undefined';
export const F = {
  display: WEB ? 'Inter, Roboto, system-ui, sans-serif' : undefined, // one clean sans-serif everywhere
  sans: WEB ? 'Inter, Roboto, system-ui, sans-serif' : undefined,
};
F.serif = F.display; // older name
export const R = { xl: 28, lg: 22, md: 16, sm: 12, pill: 999 };
// soft, warm shadow for floating surfaces (barely visible in dark mode, where layers do the work)
export const SH = THEME === 'light'
  ? { shadowColor: C.shadow, shadowOpacity: 0.07, shadowRadius: 28, shadowOffset: { width: 0, height: 10 }, elevation: 3 }
  : { shadowColor: '#000000', shadowOpacity: 0.35, shadowRadius: 24, shadowOffset: { width: 0, height: 10 }, elevation: 4 };
export const SH_SM = THEME === 'light'
  ? { shadowColor: C.shadow, shadowOpacity: 0.05, shadowRadius: 16, shadowOffset: { width: 0, height: 4 }, elevation: 1 }
  : { shadowColor: '#000000', shadowOpacity: 0.25, shadowRadius: 10, shadowOffset: { width: 0, height: 4 }, elevation: 2 };
// pastel pairs for icon tiles and highlight cards, in a fixed order so screens look calm, not random
export const PASTELS = [
  { bg: C.lavender, fg: C.lavenderText },
  { bg: C.peach, fg: C.peachText },
  { bg: C.sage, fg: C.sageText },
  { bg: C.butter, fg: C.butterText },
  { bg: C.sky, fg: C.skyText },
];
export const pastel = (i) => PASTELS[((i % PASTELS.length) + PASTELS.length) % PASTELS.length];

// ---------------------------------------------------------------- CPCB categories
// standard CPCB hues, softened to sit on ivory and charcoal; fg = readable text on the colour
export const CAT = {
  Good: { bg: '#4fb477', fg: '#1b160f' },
  Satisfactory: { bg: '#a9cc55', fg: '#1b160f' },
  Moderate: { bg: '#f0c33c', fg: '#1b160f' },
  Poor: { bg: '#f08b3e', fg: '#1b160f' },
  'Very Poor': { bg: '#dc4f52', fg: '#1b160f' },
  Severe: { bg: '#9e2f38', fg: '#ffffff' },
};
export const CAT_ORDER = ['Good', 'Satisfactory', 'Moderate', 'Poor', 'Very Poor', 'Severe'];
export const catStyle = (c) => CAT[c] || { bg: THEME === 'light' ? '#c7cad1' : '#3a3d45', fg: C.text };
// category name written as coloured text on the page: deeper shades on ivory, lighter on charcoal
const CAT_TEXT = {
  light: { Good: '#256b3f', Satisfactory: '#4a6312', Moderate: '#735600', Poor: '#9a4612', 'Very Poor': '#a8282d', Severe: '#86232b' },
  dark: { Good: '#7ed29c', Satisfactory: '#c2de7a', Moderate: '#f5d46a', Poor: '#f6a86b', 'Very Poor': '#f08a8c', Severe: '#e77c84' },
};
export const catText = (c) => CAT_TEXT[THEME][c] || C.text;
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
