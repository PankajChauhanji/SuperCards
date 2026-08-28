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

/* Bump on every deploy that changes JS. Static assets are stale-while-revalidate,
   so without a bump a returning player runs the PREVIOUS build's JavaScript for a
   whole page load — and a client speaking an older protocol to a newer server is
   indistinguishable, from the player's seat, from the state-desync bug this cache
   name was last bumped for. `activate` purges every cache that is not this one,
   so changing the name is what forces a clean fetch. */
const CACHE_NAME = "super-cards-v6";

/* Static assets to pre-cache on install for instant second loads. */
const PRECACHE_URLS = [
  "/",
  "/static/css/base.css",
  "/static/css/lobby.css",
  "/static/css/table.css",
  "/static/css/reactions.css",
  "/static/css/themes.css",
  "/static/css/safe-area.css",
  "/static/js/vendor/socket.io.min.js",
  "/static/js/core/identity.js",
  "/static/js/core/socket.js",
  "/static/js/core/install.js",
  "/static/js/core/connection.js",
  "/static/js/core/waking.js",
  "/static/js/home.js",
  "/static/img/super_cards_symbol.svg",
  "/static/icons/super_cards_icon.svg",
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

  /* The landing page is safe to serve from cache instantly — it is identical for
     everyone. Doing so is what makes a cold launch paint immediately instead of
     waiting out the host's wake-up. */
  if (url.pathname === "/") {
    event.respondWith(cacheFirstRace(event.request, 2500));
    return;
  }

  /* Room pages carry server-rendered game_type + code, and a 4-char room code
     gets reused. Serving a stale one would boot the player into the wrong game's
     bundle, so these stay strictly network-first. By the time anyone opens a room
     the server is awake anyway. */
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

/* Paint from cache, but give the network a short head start so a warm server
   still wins and the page is never needlessly stale.

   A sleeping free-tier instance does not fail — it stalls for 20-50s. A plain
   network-first therefore blocks on the full nap. Racing a timeout turns that
   into an instant paint, with the fresh copy landing in cache for next time. */
async function cacheFirstRace(request, timeoutMs) {
  const cache = await caches.open(CACHE_NAME);
  const cached = await cache.match(request);

  const network = fetch(request)
    .then((response) => {
      if (response.ok) cache.put(request, response.clone());
      return response;
    })
    .catch(() => null);

  if (!cached) return (await network) || networkFirst(request);

  const timeout = new Promise((resolve) => setTimeout(() => resolve(null), timeoutMs));
  return (await Promise.race([network, timeout])) || cached;
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
