// Talks to the project's FastAPI backend running on the laptop (python -m uvicorn backend.app:app --host 0.0.0.0 --port 8000).
import Constants from 'expo-constants';

// Expo Go loads the app from the laptop, so the laptop's Wi-Fi address is known: use the same address with port 8000.
export const OFFLINE_SERVER = 'offline://demo';
export const offlineAvailable = () => typeof globalThis !== 'undefined' && !!globalThis.__AQ_OFFLINE;
export const isOffline = (url) => String(url || '').startsWith('offline://');

export function guessServer() {
  if (typeof globalThis !== 'undefined' && globalThis.__AQ_DEFAULT_SERVER) return globalThis.__AQ_DEFAULT_SERVER;
  try {
    const h =
      (Constants.expoConfig && Constants.expoConfig.hostUri) ||
      (Constants.manifest2 && Constants.manifest2.extra && Constants.manifest2.extra.expoGo && Constants.manifest2.extra.expoGo.debuggerHost) ||
      (Constants.manifest && Constants.manifest.debuggerHost) ||
      '';
    const host = String(h).split(':')[0];
    if (/^\d+\.\d+\.\d+\.\d+$/.test(host)) return `http://${host}:8000`;
  } catch (e) {
    // ignore
  }
  return 'http://192.168.1.2:8000';
}

let BASE = '';
export function setServer(url) {
  BASE = String(url || '').trim().replace(/\/+$/, '');
  if (BASE && !/^(https?|offline):\/\//.test(BASE)) BASE = 'http://' + BASE;
}
export const getServer = () => BASE;

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

async function request(path, options = {}, timeoutMs = 12000) {
  const ctrl = typeof AbortController !== 'undefined' ? new AbortController() : null;
  const timer = setTimeout(() => ctrl && ctrl.abort(), timeoutMs);
  let res;
  try {
    res = await fetch(BASE + path, { ...options, signal: ctrl ? ctrl.signal : undefined });
  } catch (e) {
    throw new ApiError('Cannot reach the server at ' + BASE + '. Is the laptop server running and on the same Wi-Fi?', 0);
  } finally {
    clearTimeout(timer);
  }
  let body = null;
  try {
    body = await res.json();
  } catch (e) {
    body = null;
  }
  if (!res.ok) throw new ApiError((body && body.detail) || 'Server error ' + res.status, res.status);
  return body;
}

const qs = (o) =>
  Object.entries(o)
    .filter(([, v]) => v !== undefined && v !== null && v !== '')
    .map(([k, v]) => encodeURIComponent(k) + '=' + encodeURIComponent(v))
    .join('&');

export const api = {
  ping: () => request('/api/stations', {}, 6000),
  meta: () => request('/api/meta'),
  hours: (period, station) => request('/api/replay/hours?' + qs({ period, station })),
  events: (period, station, alert_from) => request('/api/replay/events?' + qs({ period, station, alert_from })),
  replayState: (period, station, t, groups, alert_from) =>
    request('/api/replay/state?' + qs({ period, station, t, groups: (groups || []).join(','), alert_from })),
  stationsNow: (mode, t) => request('/api/stations/now?' + qs({ mode, t })),
  weekly: (station, mode, t, groups) => request('/api/weekly?' + qs({ station, mode, t, groups: (groups || []).join(',') })),
  liveState: (station) => request('/api/live/state?' + qs({ station })),
  liveAdvice: (aqi, body) =>
    request('/api/advice?' + qs({ aqi }), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
};
