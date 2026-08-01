/**
 * Super Cards — Service Worker
 *
 * Strategy:
 *  - Static assets (CSS, JS, images, fonts): Stale-while-revalidate — serve
 *    from cache instantly, update in the background for next load.
 *  - HTML pages: Network-first — always get the freshest page, fall back to
 *    cache if offline.
 *  - Socket.IO / WebSocket: Never intercepted — pass through directly.
 *  - API / dynamic: Network-only.
 *
 * The primary purpose is installability (Add to Home Screen) and faster
 * repeat loads.  Offline play is not supported since the game requires a
 * live server connection for multiplayer.
 */

const CACHE_NAME = "super-cards-v1";

/* Static assets to pre-cache on install for instant second loads. */
const PRECACHE_URLS = [
  "/",
  "/static/css/base.css",
  "/static/css/lobby.css",
  "/static/css/table.css",
  "/static/css/reactions.css",
  "/static/css/themes.css",
  "/static/js/vendor/socket.io.min.js",
  "/static/js/core/identity.js",
  "/static/js/core/socket.js",
  "/static/js/home.js",
  "/static/img/super_cards_symbol.svg",
  "/static/icons/icon.svg",
];

/* ── Install ─────────────────────────────────────────────────────────── */
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(PRECACHE_URLS))
  );
  /* Activate immediately — don't wait for old tabs to close. */
  self.skipWaiting();
});

/* ── Activate ────────────────────────────────────────────────────────── */
self.addEventListener("activate", (event) => {
  /* Purge stale caches from previous versions. */
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key !== CACHE_NAME)
          .map((key) => caches.delete(key))
      )
    )
  );
  /* Take control of open tabs immediately. */
  self.clients.claim();
});

/* ── Fetch ───────────────────────────────────────────────────────────── */
self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  /* Never intercept Socket.IO polling, WebSocket upgrades, or POST
     requests — these are real-time game traffic. */
  if (
    event.request.method !== "GET" ||
    url.pathname.startsWith("/socket.io") ||
    url.protocol === "ws:" ||
    url.protocol === "wss:"
  ) {
    return;
  }

  /* Static assets → stale-while-revalidate. */
  if (url.pathname.startsWith("/static/")) {
    event.respondWith(staleWhileRevalidate(event.request));
    return;
  }

  /* HTML pages → network-first with cache fallback. */
  event.respondWith(networkFirst(event.request));
});

/* ── Strategies ──────────────────────────────────────────────────────── */

async function staleWhileRevalidate(request) {
  const cache = await caches.open(CACHE_NAME);
  const cached = await cache.match(request);

  /* Fire-and-forget: update the cache in the background. */
  const fetching = fetch(request)
    .then((response) => {
      if (response.ok) {
        cache.put(request, response.clone());
      }
      return response;
    })
    .catch(() => cached);

  /* Return the cached version immediately, or wait for network. */
  return cached || fetching;
}

async function networkFirst(request) {
  try {
    const response = await fetch(request);
    /* Cache successful HTML responses for offline fallback. */
    if (response.ok) {
      const cache = await caches.open(CACHE_NAME);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    const cached = await caches.match(request);
    if (cached) return cached;

    /* Ultimate fallback: a simple offline notice. */
    return new Response(
      `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Super Cards — Offline</title>
  <style>
    body {
      font-family: "Inter", system-ui, sans-serif;
      background: #0f1f1c;
      color: #e7efe9;
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      margin: 0;
      text-align: center;
      padding: 2rem;
    }
    .offline {
      max-width: 360px;
    }
    .offline h1 {
      font-family: "Space Grotesk", system-ui, sans-serif;
      font-size: 1.6rem;
      margin-bottom: 0.75rem;
    }
    .offline p {
      color: #93a9a1;
      line-height: 1.6;
    }
    .retry {
      display: inline-block;
      margin-top: 1.5rem;
      padding: 0.75rem 2rem;
      background: #e6b23c;
      color: #15201d;
      border: none;
      border-radius: 10px;
      font-weight: 600;
      font-size: 1rem;
      cursor: pointer;
      text-decoration: none;
    }
  </style>
</head>
<body>
  <div class="offline">
    <h1>🃏 You're Offline</h1>
    <p>Super Cards needs an internet connection for multiplayer games. Check your connection and try again.</p>
    <a href="/" class="retry">Retry</a>
  </div>
</body>
</html>`,
      { status: 503, headers: { "Content-Type": "text/html; charset=utf-8" } }
    );
  }
}
