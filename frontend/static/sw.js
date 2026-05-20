// KONTACT service worker — cache shell, network-first for API, offline fallback.
const CACHE_NAME = 'kontact-v3';
const SHELL = [
  '/',
  '/upload',
  '/queue',
  '/chat',
  '/data',
  '/manifest.json',
  '/icon.svg',
  '/icons/icon-192.png',
  '/icons/icon-512.png',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL).catch(() => {}))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);

  // API: network-only (no stale data); fall back to JSON error when offline
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(
      fetch(req).catch(() =>
        new Response(JSON.stringify({ offline: true }), {
          status: 503,
          headers: { 'content-type': 'application/json' },
        })
      )
    );
    return;
  }

  // Thumbs/images: cache-first w/ network refresh
  if (url.pathname.startsWith('/api/thumb/') || url.pathname.startsWith('/api/image/')) {
    event.respondWith(
      caches.match(req).then((cached) => {
        const fetched = fetch(req).then((resp) => {
          if (resp.ok) {
            const clone = resp.clone();
            caches.open(CACHE_NAME).then((c) => c.put(req, clone));
          }
          return resp;
        }).catch(() => cached);
        return cached || fetched;
      })
    );
    return;
  }

  // App shell: network-first, fall back to cache, then offline page
  event.respondWith(
    fetch(req).then((resp) => {
      if (resp.ok) {
        const clone = resp.clone();
        caches.open(CACHE_NAME).then((c) => c.put(req, clone));
      }
      return resp;
    }).catch(() =>
      caches.match(req).then((cached) =>
        cached || caches.match('/') || new Response('Offline', { status: 503 })
      )
    )
  );
});
