/**
 * A3: Service Worker — offline cache and last-known dashboard state.
 *
 * Strategy:
 *  - Static assets: Cache-first (cache wins, network fallback).
 *  - API data:      Network-first (serve stale on failure).
 *
 * The "offline" banner is shown by the main app when navigator.onLine is false
 * and the SW returns a cached response.
 */

const CACHE_VERSION = "v2";
const STATIC_CACHE = `static-${CACHE_VERSION}`;
const DATA_CACHE = `data-${CACHE_VERSION}`;

const STATIC_ASSETS = [
  "/",
  "/index.html",
];

// Install — pre-cache static shell
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) => cache.addAll(STATIC_ASSETS)),
  );
  self.skipWaiting();
});

// Activate — evict old caches
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((k) => k !== STATIC_CACHE && k !== DATA_CACHE)
          .map((k) => caches.delete(k)),
      ),
    ),
  );
  self.clients.claim();
});

// Fetch
self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Static assets — cache-first
  if (
    request.method === "GET" &&
    (url.pathname === "/" ||
      url.pathname.startsWith("/assets/") ||
      url.pathname.endsWith(".html"))
  ) {
    event.respondWith(
      caches.match(request).then(
        (cached) =>
          cached ??
          fetch(request).then((response) => {
            if (response.ok) {
              caches
                .open(STATIC_CACHE)
                .then((cache) => cache.put(request, response.clone()));
            }
            return response;
          }),
      ),
    );
    return;
  }

  // API data — network-first, fall back to cache
  if (request.method === "GET" && url.pathname.startsWith("/api/")) {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response.ok) {
            // Clone *before* returning so the body isn't already consumed
            const toCache = response.clone();
            caches.open(DATA_CACHE).then((cache) => cache.put(request, toCache));
          }
          return response;
        })
        .catch(() => caches.match(request)),
    );
  }
});
