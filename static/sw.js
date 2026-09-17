// De jungen Olen – Service Worker v4
// Features: Push Notifications, Offline Map Tiles, Asset Caching

const CACHE_VERSION = 'djo-v4';
const TILE_CACHE    = 'djo-tiles-v1';
const SHELL_ASSETS  = [
  '/',
  '/static/css/style.css',
  '/static/logo.png',
  '/static/manifest.json',
];

// ── Install ───────────────────────────────────────────────────────────────────
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_VERSION).then(cache =>
      Promise.allSettled(SHELL_ASSETS.map(url =>
        cache.add(url).catch(() => {})
      ))
    )
  );
  self.skipWaiting();
});

// ── Activate ──────────────────────────────────────────────────────────────────
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys.filter(k => k !== CACHE_VERSION && k !== TILE_CACHE)
            .map(k => caches.delete(k))
      )
    )
  );
  self.clients.claim();
});

// ── Fetch ─────────────────────────────────────────────────────────────────────
self.addEventListener('fetch', event => {
  const req = event.request;
  const url = new URL(req.url);
  if (req.method !== 'GET') return;

  // Map Tiles: cache-first mit langer Lebensdauer (OpenStreetMap)
  if (url.hostname.includes('tile.openstreetmap.org') ||
      url.hostname.includes('tile.opentopomap.org') ||
      url.hostname.includes('tiles.wmflabs.org')) {
    event.respondWith(
      caches.open(TILE_CACHE).then(cache =>
        cache.match(req).then(cached => {
          if (cached) return cached;
          return fetch(req).then(resp => {
            if (resp.ok) cache.put(req, resp.clone());
            return resp;
          }).catch(() => cached || new Response('', {status: 408}));
        })
      )
    );
    return;
  }

  // Static Assets + CDN: cache-first
  if (url.pathname.startsWith('/static/') ||
      url.hostname.includes('cdn.') || url.hostname.includes('unpkg.com') ||
      url.hostname.includes('cdnjs.cloudflare.com')) {
    event.respondWith(
      caches.match(req).then(c => c || fetch(req).then(resp => {
        if (resp.ok) caches.open(CACHE_VERSION).then(cache => cache.put(req, resp.clone()));
        return resp;
      }).catch(() => new Response('', {status: 408})))
    );
    return;
  }

  // Fotos/Videos: cache-first
  if (url.pathname.startsWith('/static/uploads/') ||
      url.pathname.startsWith('/fotos/') || url.pathname.startsWith('/videos/')) {
    event.respondWith(
      caches.match(req).then(c => c || fetch(req).then(resp => {
        if (resp.ok) caches.open(CACHE_VERSION).then(cache => cache.put(req, resp.clone()));
        return resp;
      }))
    );
    return;
  }

  // API-Calls: network-only (kein Cache)
  if (url.pathname.startsWith('/api/')) return;

  // HTML-Seiten: network-first, Fallback auf Cache
  event.respondWith(
    fetch(req).then(resp => {
      if (resp.ok) caches.open(CACHE_VERSION).then(c => c.put(req, resp.clone()));
      return resp;
    }).catch(() =>
      caches.match(req).then(c => c || caches.match('/'))
    )
  );
});

// ── Push Notifications ────────────────────────────────────────────────────────
self.addEventListener('push', event => {
  if (!event.data) return;

  let data = {};
  try { data = event.data.json(); } catch { data = {title: 'De jungen Olen', body: event.data.text()}; }

  const options = {
    body:    data.body || '',
    icon:    '/static/logo.png',
    badge:   '/static/logo.png',
    vibrate: [200, 100, 200],
    data:    { url: data.url || '/' },
    actions: [
      { action: 'open',    title: 'Öffnen' },
      { action: 'dismiss', title: 'Schließen' },
    ]
  };

  event.waitUntil(
    self.registration.showNotification(data.title || 'De jungen Olen', options)
  );
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  if (event.action === 'dismiss') return;
  const url = event.notification.data?.url || '/';
  event.waitUntil(
    clients.matchAll({type: 'window', includeUncontrolled: true}).then(windowClients => {
      for (const client of windowClients) {
        if (client.url.includes(self.location.origin) && 'focus' in client) {
          client.navigate(url);
          return client.focus();
        }
      }
      return clients.openWindow(url);
    })
  );
});

// ── Offline Tile Prefetch (auf Anfrage) ───────────────────────────────────────
self.addEventListener('message', event => {
  if (event.data?.type === 'PREFETCH_TILES') {
    // GPX-Bounding-Box als Kacheln voraus-cachen
    const {tiles} = event.data;
    if (!tiles || !tiles.length) return;
    caches.open(TILE_CACHE).then(cache => {
      tiles.forEach(url => {
        fetch(url).then(r => { if (r.ok) cache.put(url, r); }).catch(() => {});
      });
    });
    event.ports[0]?.postMessage({ok: true, count: tiles.length});
  }
});
