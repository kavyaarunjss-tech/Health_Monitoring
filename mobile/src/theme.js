// Design system: colour tokens, type, radii, shadows and the theme engine (Light / Dark / System).
// Warm editorial look: ivory and cream in light mode, layered charcoal with soft glows in dark mode.
// CPCB category colours are the only strong colours; every text/background pair here was checked for WCAG AA (4.5:1).
import { Appearance } from 'react-native';

const LIGHT = {
  bg: '#f6f1e9', // warm ivory page
  bg2: '#efe7db', // cream band
  card: '#fffcf7', // raised surface
  card2: '#efe7db', // inset surface (chips, tracks)
  line: '#e7ded0',
  nav: '#fffcf7',
  text: '#1e1b18',
  soft: '#4a433c',
  muted: '#665e55',
  faint: '#71685e',
  accent: '#a2482a', // clay: links and active states
  accentBg: '#f8dcc9',
  selBg: '#f8e6d8',
  selBorder: '#d9a283',
  good: '#2e6a3d',
  warnBg: '#fbe5d4',
  warnText: '#7a3410',
  warnIcon: '#a8501c',
  dangerBg: '#f8ddda',
  danger: '#a8282d',
  dangerText: '#7d1c17',
  infoBg: '#e3ebf2',
  infoText: '#22405b',
  strong: '#1e1b18',
  onPrimary: '#fffcf7', // text on the ink button
  primary: '#1e1b18',
  shadow: '#5b4a36',
  // pastel accents (backgrounds only; text on them uses tintText)
  sage: '#dde8d6',
  lavender: '#e6e0f4',
  peach: '#f8dcc9',
  butter: '#f5e8bf',
  sky: '#e3ebf2',
  sageText: '#2c4a2f',
  lavenderText: '#3c3166',
  peachText: '#6e3416',
  butterText: '#5a4710',
  skyText: '#22405b',
  glowA: 'rgba(242,168,116,0.20)',
  glowB: 'rgba(186,170,236,0.16)',
};
const DARK = {
  bg: '#121110', // near-black charcoal
  bg2: '#171614',
  card: '#1c1a18', // layered surfaces
  card2: '#272421',
  line: '#2e2a26',
  nav: '#1c1a18',
  text: '#f3eee7',
  soft: '#d2cac0',
  muted: '#a99f94',
  faint: '#988e83',
  accent: '#f2b48f', // the same clay, lifted to peach
  accentBg: '#2c1f18',
  selBg: '#2c1f18',
  selBorder: '#8a5a3e',
  good: '#9dd3a9',
  warnBg: '#2f2017',
  warnText: '#f6cbae',
  warnIcon: '#f2a874',
  dangerBg: '#2e1817',
  danger: '#f08a8c',
  dangerText: '#f5bdb9',
  infoBg: '#19222c',
  infoText: '#c5d7ea',
  strong: '#ffffff',
  onPrimary: '#1b1917',
  primary: '#f3eee7',
  shadow: '#000000',
  sage: '#1d2620',
  lavender: '#221f2e',
  peach: '#2c1f18',
  butter: '#29251a',
  sky: '#19222c',
  sageText: '#c7dec6',
  lavenderText: '#d6ccf4',
  peachText: '#f3c9ae',
  butterText: '#eedb9f',
  skyText: '#c5d7ea',
  glowA: 'rgba(240,170,120,0.16)',
  glowB: 'rgba(160,140,235,0.12)',
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
  serif: WEB ? 'Lora, Georgia, serif' : 'serif', // editorial display: headlines and the big AQI
  sans: WEB ? 'Inter, Roboto, system-ui, sans-serif' : undefined,
};
export const R = { xl: 28, lg: 22, md: 16, sm: 12, pill: 999 };
// soft, warm shadow for floating surfaces (barely visible in dark mode, where layers do the work)
export const SH = THEME === 'light'
  ? { shadowColor: C.shadow, shadowOpacity: 0.08, shadowRadius: 24, shadowOffset: { width: 0, height: 8 }, elevation: 3 }
  : { shadowColor: '#000000', shadowOpacity: 0.35, shadowRadius: 24, shadowOffset: { width: 0, height: 10 }, elevation: 4 };
export const SH_SM = THEME === 'light'
  ? { shadowColor: C.shadow, shadowOpacity: 0.06, shadowRadius: 10, shadowOffset: { width: 0, height: 3 }, elevation: 1 }
  : { shadowColor: '#000000', shadowOpacity: 0.25, shadowRadius: 10, shadowOffset: { width: 0, height: 4 }, elevation: 2 };
// pastel pairs for icon tiles and highlight cards, in a fixed order so screens look calm, not random
export const PASTELS = [
  { bg: C.peach, fg: C.peachText },
  { bg: C.sage, fg: C.sageText },
  { bg: C.lavender, fg: C.lavenderText },
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
export const catStyle = (c) => CAT[c] || { bg: THEME === 'light' ? '#b9b0a4' : '#4a4540', fg: C.text };
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
