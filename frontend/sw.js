/* Service worker (PWA, 26 Oct 2026).
   - Static files (scripts, styles, fonts, icons, vendor): CACHE-FIRST. Their links carry ?v=... versions, so a new version is a new URL and is
     fetched from the server.
   - Pages (HTML navigations): NETWORK-FIRST (they are login-gated); the last copy is used only when the server cannot be reached.
   - ALL API / data requests (/api/...): NETWORK-FIRST. A successful answer is saved with the time it was received; when the server cannot be
     reached the saved copy is returned with the header "X-AQI-Offline: 1" and its "X-AQI-Saved-At" time, and the page shows
     "Offline - showing data from <time>". A saved copy is never presented as current.
   - Never cached: login / account / push / e-mail endpoints (except who-is-logged-in), and every non-GET request.
   - Push: shows the alert notification; tapping it opens (or focuses) the alert page. */
const VERSION = "v3";                 // v2 (26 Oct 2026): monochrome badge icon; bump when un-versioned files (icons, fonts) change
const STATIC = "aqi-static-" + VERSION, PAGES = "aqi-pages-" + VERSION, DATA = "aqi-data-" + VERSION;
// never cached: login / verify / reset links, own account, push, e-mail, profile. /api/auth/session (who is logged in) IS kept network-first so an
// offline page still shows the same profile's advice.
const NEVER_CACHE = [/^\/api\/auth\/(?!session$)/, /^\/api\/me(\/|$)/, /^\/api\/push\//, /^\/api\/email\//, /^\/api\/profile/, /^\/api\/scheduler\/run-now/];

self.addEventListener("install", (e) => { self.skipWaiting(); });
self.addEventListener("activate", (e) => {
  e.waitUntil((async () => {
    for (const k of await caches.keys()) if (![STATIC, PAGES, DATA].includes(k)) await caches.delete(k);
    await self.clients.claim();
  })());
});

async function networkFirstData(req) {
  const cache = await caches.open(DATA);
  try {
    const res = await fetch(req);
    if (res.ok) {
      const body = await res.clone().arrayBuffer();
      const h = new Headers(res.headers);
      h.set("X-AQI-Saved-At", new Date().toISOString());
      await cache.put(req, new Response(body, { status: res.status, statusText: res.statusText, headers: h }));
    }
    return res;
  } catch (err) {
    const hit = await cache.match(req);
    if (!hit) throw err;
    const h = new Headers(hit.headers);
    h.set("X-AQI-Offline", "1");
    return new Response(await hit.arrayBuffer(), { status: hit.status, statusText: hit.statusText, headers: h });
  }
}

async function networkFirstPage(req) {
  const cache = await caches.open(PAGES);
  try {
    const res = await fetch(req);
    if (res.ok && !res.redirected) await cache.put(new URL(req.url).pathname, res.clone());   // one copy per page (query ignored)
    return res;
  } catch (err) {
    const hit = await cache.match(new URL(req.url).pathname);
    if (hit) return hit;
    throw err;
  }
}

async function cacheFirst(req) {
  const cache = await caches.open(STATIC);
  const hit = await cache.match(req);
  if (hit) return hit;
  const res = await fetch(req);
  if (res.ok) await cache.put(req, res.clone());
  return res;
}

self.addEventListener("fetch", (e) => {
  const req = e.request, url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== self.location.origin) return;          // let the browser handle it (never cached)
  if (url.pathname.startsWith("/api/")) {
    if (NEVER_CACHE.some((re) => re.test(url.pathname))) return;
    e.respondWith(networkFirstData(req));
  } else if (req.mode === "navigate" || url.pathname.endsWith(".html") || url.pathname === "/") {
    e.respondWith(networkFirstPage(req));
  } else if (url.pathname === "/sw.js") {
    return;
  } else {
    e.respondWith(cacheFirst(req));
  }
});

/* ---------- Web Push ---------- */
self.addEventListener("push", (e) => {
  let p = {};
  try { p = e.data ? e.data.json() : {}; } catch (err) { p = { title: "AQ Health", body: e.data ? e.data.text() : "" }; }
  e.waitUntil(self.registration.showNotification(p.title || "AQ Health alert", {
    body: p.body || "", tag: p.tag || "aqi-alert", renotify: true, icon: "/icons/icon-192.png", badge: "/icons/badge-96.png",
    data: { url: p.url || "/" },
  }));
});
self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  const target = new URL((e.notification.data && e.notification.data.url) || "/", self.location.origin).href;
  e.waitUntil((async () => {
    const wins = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    for (const w of wins) {
      if ("navigate" in w) { await w.focus(); return w.navigate(target); }
    }
    return self.clients.openWindow(target);
  })());
});
