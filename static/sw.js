// Notfic — minimal service worker (PWA ornatilishi uchun zarur)
// Sorovlarni ushlab qolmaydi, faqat "fetch" tinglovchisi borligini taminlaydi.

self.addEventListener('install', function (event) {
    self.skipWaiting();
});

self.addEventListener('activate', function (event) {
    event.waitUntil(self.clients.claim());
});

self.addEventListener('fetch', function (event) {
    // Qasddan bosh qoldirilgan — sorovlar tabiiy holda internetga otkaziladi.
});