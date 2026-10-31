// Runs before the app inside the Android WebView.
// 1) "offline://demo" server: answers the app's /api/... requests from real backend responses packed in assets/www/data.
// 2) any other server: requests go through the Android bridge (native HTTP, no browser CORS rules).
(function () {
  const A = window.AQAndroid || null;
  window.__AQ_OFFLINE = true;
  window.__AQ_DEFAULT_SERVER = 'offline://demo';
  window.__INSETS = { top: 0, bottom: 0 };

  function readText(path) {
    if (A && A.readAsset) return Promise.resolve(A.readAsset('www/' + path));
    return fetch(path).then((r) => r.text());
  }
  let common = null;
  const stations = {};
  const loadCommon = () => common ? Promise.resolve(common) : readText('data/common.json').then((t) => (common = JSON.parse(t)));
  const loadStation = (id) => stations[id] ? Promise.resolve(stations[id]) : readText('data/st_' + id + '.json').then((t) => (stations[id] = JSON.parse(t)));

  const ORDER = ['lung', 'heart', 'pregnant', 'child', 'older', 'outdoor_worker', 'athlete'];
  const primary = (g) => { const set = (g || '').split(',').filter(Boolean); return ORDER.find((x) => set.includes(x)) || 'none'; };
  const resp = (status, obj) => new Response(JSON.stringify(obj), { status, headers: { 'Content-Type': 'application/json' } });
  const lastDay = (t) => { const d = new Date(t.replace(' ', 'T') + 'Z'); if (d.getUTCHours() !== 23) d.setUTCDate(d.getUTCDate() - 1); return d.toISOString().slice(0, 10); };

  async function offline(url) {
    const u = new URL(url.replace('offline://demo', 'http://offline'));
    const q = Object.fromEntries(u.searchParams.entries());
    const p = u.pathname;
    const c = await loadCommon();
    if (p === '/api/stations') return resp(200, c.stations);
    if (p === '/api/meta') return resp(200, c.meta);
    if (p === '/api/periods') return resp(200, c.periods);
    if (p.startsWith('/api/live/') || q.mode === 'live') return resp(503, { detail: 'Built-in demo data has no live mode. Live data needs the laptop server (Profile → Laptop server).' });
    if (p === '/api/replay/hours') return resp(200, { hours: q.period === c.window.period ? (c.hours[q.station] || []) : [] });
    if (p === '/api/replay/events') {
      const lv = Number(q.alert_from || 101);
      const keys = Object.keys(c.events[q.station] || {}).map(Number).sort((a, b) => a - b);
      const k = keys.reduce((best, x) => (Math.abs(x - lv) < Math.abs(best - lv) ? x : best), keys[0]);
      return resp(200, (c.events[q.station] || {})[String(k)] || { onsets: [] });
    }
    if (p === '/api/stations/now') return resp(200, c.stationsNow[q.t] || { stations: [] });
    if (p === '/api/replay/state') {
      const s = await loadStation(q.station);
      const b = s.base[q.t];
      if (!b) return resp(404, { detail: 'This hour is outside the built-in demo (22-25 Apr 2026).' });
      const g = s.personal[q.t][primary(q.groups)] || s.personal[q.t].none;
      return resp(200, { ...b, personal: g.personal, advice: g.advice });
    }
    if (p === '/api/weekly') {
      const s = await loadStation(q.station);
      const w = s.weekly[lastDay(q.t)] || s.weekly[Object.keys(s.weekly)[0]];
      return resp(200, w[primary(q.groups)] || w.none);
    }
    if (p === '/api/advice') return resp(503, { detail: 'Not available in the built-in demo.' });
    return resp(404, { detail: 'not found' });
  }

  // native HTTP through the Android bridge
  const pending = {};
  let seq = 0;
  window.__aqNetDone = function (id, status, body) {
    const f = pending[id];
    delete pending[id];
    if (!f) return;
    if (status === 0) f.reject(new TypeError('Network request failed'));
    else f.resolve(new Response(body, { status, headers: { 'Content-Type': 'application/json' } }));
  };
  function bridged(url, opts) {
    return new Promise((resolve, reject) => {
      const id = ++seq;
      pending[id] = { resolve, reject };
      A.http(id, url, (opts && opts.method) || 'GET', (opts && opts.body) || '');
      setTimeout(() => window.__aqNetDone(id, 0, ''), 15000);
    });
  }

  const realFetch = window.fetch.bind(window);
  window.fetch = function (url, opts) {
    url = String(url);
    if (url.startsWith('offline://')) return offline(url);
    if (A && A.http && /^https?:\/\//.test(url)) return bridged(url, opts);
    return realFetch(url, opts);
  };

  // phone notifications through the bridge
  window.__aqNotify = function (title, body) {
    if (A && A.showAlert) { A.showAlert(title, body); return true; }
    if ('Notification' in window && Notification.permission === 'granted') { new Notification(title, { body }); return true; }
    return false;
  };
  // e-mail alerts: sent by the phone through Gmail (MailSender.java); the App password stays in Android storage
  if (A && A.sendMail) {
    const mailPending = {};
    let mailSeq = 0;
    window.__aqMailDone = function (id, ok, message) {
      const f = mailPending[id];
      delete mailPending[id];
      if (f) f({ ok: !!ok, message: String(message || '') });
    };
    window.__aqMail = {
      status() {
        try { return JSON.parse(A.mailStatus()); } catch (e) { return { configured: false, sender: '' }; }
      },
      save(user, pass) { return String(A.saveMailSender(user || '', pass || '') || ''); },
      clear() { A.clearMailSender(); },
      send(to, subject, text, html) {
        return new Promise((resolve) => {
          const id = ++mailSeq;
          mailPending[id] = resolve;
          A.sendMail(id, to || '', subject || '', text || '', html || '');
          setTimeout(() => window.__aqMailDone(id, false, 'No answer from the mail server after 60 s. Check the internet connection.'), 60000);
        });
      },
    };
  }
  window.__aqOpen = function (url) {
    if (A && A.openUrl) A.openUrl(url); else window.open(url, '_blank');
  };
})();
