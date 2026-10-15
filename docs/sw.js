/* Class Base service worker. Keeps the hosted app working offline once it has been opened.
 *
 * - Every file in PRECACHE is cached together under one version; requests for them are answered from that cache.
 * - VERSION is a hash of those files, written by `python build.py --site`. When any of them changes, this file
 *   changes, so browsers install the new version.
 * - A new version waits until the page asks it to take over (the "new version" toast's Reload button),
 *   so a search in progress is never swapped out from under the user.
 * - Cache names start with "classBase-": every GitHub Pages project of this user shares the origin.
 * - Added PDFs live in IndexedDB, not here; this worker never touches them.
 */
"use strict";
const VERSION = "cb047a608d0a";
const CACHE = "classBase-" + VERSION;
const PRECACHE = [
  "./",
  "index.html",
  "manifest.webmanifest",
  "icons/apple-touch-icon.png",
  "icons/icon-192.png",
  "icons/icon-512.png",
  "icons/icon-maskable-512.png",
  "icons/icon.svg"
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(PRECACHE.map((u) => new Request(u, { cache: "reload" })))));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k.indexOf("classBase-") === 0 && k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("message", (event) => {
  if (event.data && event.data.type === "SKIP_WAITING") self.skipWaiting();
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin || !url.href.startsWith(self.registration.scope)) return;
  const precached = PRECACHE.some((p) => new URL(p, self.registration.scope).href === url.origin + url.pathname);
  if (!precached && req.mode !== "navigate") return;      // anything else: straight to the network
  event.respondWith(
    caches.open(CACHE).then((c) => c.match(req, { ignoreSearch: true })).then((hit) => hit || fetch(req))
  );
});
