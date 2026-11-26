// StepQuest service worker (owner: B, see pwa_api.py). It makes the app installable and
// lets it open without internet. It never touches /api/ calls: coins, finds and positions
// always go straight to Python, so nothing is ever out of date or paid twice.
//
// Change VERSION when the cached files change, so phones throw the old copies away.
const VERSION = "stepquest-v2";  // B: v2 throws away the old copies saved before the polish update
const SHELL = [
  "/offline",
  "/static/css/pixel.css",
  "/static/css/sprites.css",
  "/static/css/app.css",
  "/static/css/styles.css",
  "/static/js/fancy_select.js",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(VERSION).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((names) => Promise.all(names.filter((name) => name !== VERSION).map((name) => caches.delete(name))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);
  // Only our own GET requests. Never /api/ (live game data), never other sites (map tiles, fonts).
  if (request.method !== "GET" || url.origin !== self.location.origin || url.pathname.startsWith("/api/")) {
    return;
  }
  if (request.mode === "navigate") {
    // Pages: always ask the server first (they show live data); offline, show the offline page.
    event.respondWith(fetch(request).catch(() => caches.match("/offline")));
    return;
  }
  if (url.pathname.startsWith("/static/")) {
    // B: styles and scripts always come fresh when there is internet, because a new page with an
    // old stylesheet looks broken (that happened after an update). The saved copy is only for offline.
    // Pictures rarely change: the saved copy straight away, refreshed in the background.
    const code = /\.(css|js)$/.test(url.pathname);
    event.respondWith(
      caches.open(VERSION).then(async (cache) => {
        const saved = await cache.match(request);
        const fresh = fetch(request).then((response) => {
          if (response.ok) cache.put(request, response.clone());
          return response;
        });
        if (code) return fresh.catch(() => saved || Response.error());
        return saved || fresh.catch(() => Response.error());
      })
    );
  }
});
