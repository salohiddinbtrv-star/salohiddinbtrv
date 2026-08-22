// Notfic — minimal service worker (PWA ornatilishi uchun zarur)

self.addEventListener('install', function (event) {
    self.skipWaiting();
});

self.addEventListener('activate', function (event) {
    event.waitUntil(self.clients.claim());
});

self.addEventListener('fetch', function (event) {
    event.respondWith(fetch(event.request));
});