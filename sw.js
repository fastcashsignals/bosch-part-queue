const CACHE_NAME = 'bpq-v1';
const ASSETS = [
  '/bosch-part-queue/',
  '/bosch-part-queue/index.html',
  '/bosch-part-queue/manifest.json',
  '/bosch-part-queue/icon-192.png',
  '/bosch-part-queue/icon-512.png',
  '/bosch-part-queue/logo.jpg'
];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE_NAME).then(c => c.addAll(ASSETS)));
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  e.respondWith(
    caches.match(e.request).then(cached => cached || fetch(e.request))
  );
});
