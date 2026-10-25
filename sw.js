importScripts("https://cdn.onesignal.com/sdks/web/v16/OneSignalSDK.sw.js");

"use strict";

const VERSION = "2026-10-25-3";
const STATIC = `kostya-static-${VERSION}`;
const DATA = "kostya-data";

const PRECACHE = [
  "./",
  "./index.html",
  "./career.html",
  "./mama.html",
  "./styles.css",
  "./app.js",
  "./manifest.json",
  "./icon-192.png",
  "./icon-512.png",
  "./icon-maskable-192.png",
  "./icon-maskable-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(STATIC).then((cache) => cache.addAll(PRECACHE)));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys();
      await Promise.all(keys.filter((key) => key !== STATIC && key !== DATA).map((key) => caches.delete(key)));
      await self.clients.claim();
    })()
  );
});

self.addEventListener("message", (event) => {
  if (event.data && event.data.type === "SKIP_WAITING") self.skipWaiting();
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.endsWith("/sw.js")) return;
  const freshCode = /\.(?:html|js)$/.test(url.pathname) || url.pathname.endsWith("/");
  if (/\/(?:data|news)\.json$/.test(url.pathname)) {
    event.respondWith(networkFirst(request, DATA));
    return;
  }
  if (freshCode) {
    event.respondWith(networkFirst(request, STATIC));
    return;
  }
  event.respondWith(staleWhileRevalidate(event, request));
});

async function networkFirst(request, cacheName) {
  const cache = await caches.open(cacheName);
  try {
    const fresh = await fetch(request);
    if (fresh && fresh.ok) await cache.put(request, fresh.clone());
    return fresh;
  } catch (error) {
    const cached = await cache.match(request);
    if (cached) return cached;
    throw error;
  }
}

async function staleWhileRevalidate(event, request) {
  const cache = await caches.open(STATIC);
  const cached = await cache.match(request);
  const refresh = fetch(request)
    .then((response) => {
      if (response && response.ok) return cache.put(request, response.clone()).then(() => response);
      return response;
    })
    .catch(() => null);
  event.waitUntil(refresh.then(() => {}));
  if (cached) return cached;
  const fresh = await refresh;
  if (fresh) return fresh;
  return new Response("Нет сети и нет копии в кэше.", { status: 503, headers: { "Content-Type": "text/plain; charset=utf-8" } });
}
