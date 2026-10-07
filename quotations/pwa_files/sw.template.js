/*
  Service worker of the Dehlsen quotation app.   Served from /sw.js (the root, so it covers the whole app).
  The three words between double underscores are filled in by quotations/pwa.py.

  What it does - and deliberately does NOT do:
    * keeps an offline page and the icons, so the app opens to a friendly page when there is no internet
    * pages with quotations, prices and margins are NEVER stored on the phone: they always come from the server
    * forms (POST), PDF downloads and the admin always go straight to the server
    * files under /static/ are kept and refreshed in the background
*/
const VERSION = "__VERSION__";
const SHELL_CACHE = "dehlsen-shell-" + VERSION;
const STATIC_CACHE = "dehlsen-static-" + VERSION;
const OFFLINE_URL = "__OFFLINE_URL__";
const PRECACHE = __PRECACHE_JSON__;

self.addEventListener("install", function (event) {
    event.waitUntil(
        caches.open(SHELL_CACHE)
            .then(function (cache) { return cache.addAll(PRECACHE); })
            .then(function () { return self.skipWaiting(); })
    );
});

self.addEventListener("activate", function (event) {
    event.waitUntil(
        caches.keys()
            .then(function (names) {
                return Promise.all(names
                    .filter(function (name) { return name.indexOf("dehlsen-") === 0 && name !== SHELL_CACHE && name !== STATIC_CACHE; })
                    .map(function (name) { return caches.delete(name); }));
            })
            .then(function () { return self.clients.claim(); })
    );
});

self.addEventListener("fetch", function (event) {
    const request = event.request;
    const url = new URL(request.url);

    /* only plain page and file reads of this site: forms (POST) and other websites are not touched */
    if (request.method !== "GET" || url.origin !== self.location.origin) { return; }

    /* PDFs, the admin and the service worker itself: always the real thing from the server */
    if (/\/pdf$/.test(url.pathname) || url.pathname.indexOf("/admin") === 0 || url.pathname === "/sw.js") { return; }

    /* opening a page: the server first; only when there is no connection, the offline page */
    if (request.mode === "navigate") {
        event.respondWith(
            fetch(request).catch(function () { return caches.match(OFFLINE_URL); })
        );
        return;
    }

    /* static files: answer from the phone at once, and refresh the copy in the background */
    if (url.pathname.indexOf("/static/") === 0) {
        event.respondWith(
            caches.open(STATIC_CACHE).then(function (cache) {
                return cache.match(request).then(function (kept) {
                    const fresh = fetch(request).then(function (response) {
                        if (response && response.ok) { cache.put(request, response.clone()); }
                        return response;
                    }).catch(function () { return kept; });
                    return kept || fresh;
                });
            })
        );
    }
});
