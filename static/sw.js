// De jungen Olen – Service Worker
// Features: Push Notifications, Offline Map Tiles, Asset Caching
// Build ab: Der Platzhalter __BUILD__ wird von der Route /sw.js durch den aktuellen
// App-Build ersetzt – nach jedem Deploy gibt es so einen neuen Cache und die
// Browser laden CSS/JS frisch (vorher blieb 'djo-v4' über alle Builds gleich).

const CACHE_VERSION = 'djo-__BUILD__';
const TILE_CACHE    = 'djo-tiles-v1';
// Build ao (Audit 7): Kacheln wurden unbegrenzt gespeichert. Der Cache ueberlebt jedes
// Update (er steht auf der Ausnahmeliste in `activate`), und „Karte offline speichern"
// legt pro Klick bis zu 500 Kacheln ab. Auf einem Handy waechst das ueber Monate auf
// hunderte MB – dann raeumt der Browser irgendwann selbst auf, und zwar alles.
// Jetzt: harte Obergrenze, aelteste zuerst raus (FIFO).
const TILE_LIMIT    = 1500;      // ≈ 20–30 MB; genug fuer mehrere Touren offline

async function trimTileCache() {
  try {
    const cache = await caches.open(TILE_CACHE);
    const keys  = await cache.keys();
    if (keys.length <= TILE_LIMIT) return 0;
    const weg = keys.length - TILE_LIMIT;
    // Cache-Keys sind in Einfuege-Reihenfolge -> die ersten sind die aeltesten
    for (let i = 0; i < weg; i++) await cache.delete(keys[i]);
    return weg;
  } catch (e) { return 0; }
}
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
    // Build ao (Audit 7): Bei jeder neuen Build-Version einmal durchzaehmen.
    ).then(() => trimTileCache())
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
            if (resp.ok) {
              cache.put(req, resp.clone());
              // Build ao: gelegentlich aufraeumen (nicht bei jeder Kachel)
              if (Math.random() < 0.02) trimTileCache();
            }
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

  // Build ai: Fotos/Videos network-first – auf geteilten Geräten darf ein
  // ausgeloggter Browser Fotos/Videos nicht mehr aus dem Cache servieren
  // (Server antwortet dann 404 und der 404 gilt). Offline (Radtour ohne Netz)
  // fällt der Cache weiterhin ein; nie etwas nicht-okayes cachen.
  if (url.pathname.startsWith('/static/uploads/') ||
      url.pathname.startsWith('/fotos/') || url.pathname.startsWith('/videos/')) {
    event.respondWith(
      fetch(req).then(resp => {
        if (resp.ok) caches.open(CACHE_VERSION).then(cache => cache.put(req, resp.clone()));
        return resp;
      }).catch(() =>
        caches.match(req).then(c => c || new Response('', {status: 408}))
      )
    );
    return;
  }

  // API-Calls: network-only (kein Cache)
  if (url.pathname.startsWith('/api/')) return;

  // HTML-Seiten: network-first mit Zeitlimit, Fallback auf Cache.
  // Build bm: `fetch` wartete ohne Grenze – im Mobilfunknetz hing die Seite dadurch lange
  // und der Browser zeigte so lange die ALTE Seite aus dem Cache. Nach 4 s ohne Antwort
  // kommt jetzt die gespeicherte Seite; sonst immer die frische vom Server.
  event.respondWith(
    Promise.race([
      fetch(req).then(resp => {
        if (resp.ok) caches.open(CACHE_VERSION).then(c => c.put(req, resp.clone()));
        return resp;
      }),
      new Promise(resolve => setTimeout(() => resolve(null), 4000))
    ]).then(resp => resp || caches.match(req).then(c => c || fetch(req)))
      .catch(() => caches.match(req).then(c => c || caches.match('/')))
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
      // Build ao: nach dem Voraus-Cachen die Obergrenze durchsetzen
      setTimeout(() => { trimTileCache(); }, 3000);
    });
    event.ports[0]?.postMessage({ok: true, count: tiles.length});
  }
});
