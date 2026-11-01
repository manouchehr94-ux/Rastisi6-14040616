/* Service Worker اعلانِ مرورگرِ راستی‌سی. Push بدونِ Payload می‌رسد؛ محتوا را همین‌جا با نشستِ خودِ کاربر می‌خوانیم، پس هیچ داده‌ای از Push Service رد نمی‌شود.
   اگر نشست نیست/پاسخ معتبر نیست ⇒ هیچ اعلانی نشان داده نمی‌شود (نه متنِ حساس، نه متنِ عمومیِ گمراه‌کننده). */
var SUMMARY_URL = '__SUMMARY_URL__';
var INBOX_URL = '__INBOX_URL__';

self.addEventListener('install', function () { self.skipWaiting(); });
self.addEventListener('activate', function (e) { e.waitUntil(self.clients.claim()); });

self.addEventListener('push', function (event) {
  event.waitUntil((async function () {
    try {
      var r = await fetch(SUMMARY_URL, { credentials: 'same-origin', headers: { Accept: 'application/json' }, cache: 'no-store' });
      if (!r.ok || (r.headers.get('content-type') || '').indexOf('json') < 0) return;
      var d = await r.json();
      var item = null, i;
      for (i = 0; i < (d.items || []).length; i++) { if (!d.items[i].read) { item = d.items[i]; break; } }
      if (!item) return;                                              // همه خوانده شده: مزاحمت نه
      var url = INBOX_URL + item.id + '/' + (item.has_link ? 'go/' : '');
      await self.registration.showNotification(String(item.title || 'اعلان جدید').slice(0, 120), {
        tag: 'rs-' + item.id, dir: 'rtl', lang: 'fa', data: { url: url }, requireInteraction: item.severity >= 4,
      });
    } catch (e) { /* بی‌صدا: اعلانِ درون‌برنامه‌ای همچنان در دسترس است */ }
  })());
});

self.addEventListener('notificationclick', function (event) {
  event.notification.close();
  var target = (event.notification.data && event.notification.data.url) || INBOX_URL;
  if (typeof target !== 'string' || target.charAt(0) !== '/' || target.charAt(1) === '/') target = INBOX_URL;   // فقط مسیرِ همین سایت
  event.waitUntil((async function () {
    var all = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    for (var i = 0; i < all.length; i++) { if ('focus' in all[i]) { await all[i].navigate(target); return all[i].focus(); } }
    return self.clients.openWindow(target);
  })());
});
