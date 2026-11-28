importScripts("https://cdn.onesignal.com/sdks/web/v16/OneSignalSDK.sw.js");

"use strict";

const VERSION = "2026-11-28-21";
const STATIC = `kostya-static-${VERSION}`;
const DATA = `kostya-data-${VERSION}`;

const PRECACHE = [
  "./",
  "./index.html",
  "./career.html",
  "./mama.html",
  "./team.html",
  "./development.html",
  "./data.json",
  "./news.json",
  "./fonts/fonts.css?v=2026-11-28-21",
  "./fonts/xn7gYHE41ni1AdIRggOxSuXd.woff2",
  "./fonts/xn7gYHE41ni1AdIRggexSg.woff2",
  "./fonts/Yq6W-LOTXCb04q32xlpwv8ZfrxE.woff2",
  "./fonts/Yq6W-LOTXCb04q32xlpwu8Zf.woff2",
  "./styles.css?v=2026-11-28-21",
  "./app.js?v=2026-11-28-21",
  "./manifest.json?v=2026-11-28-21",
  "./favicon.svg",
  "./logo.svg",
  "./logo.png",
  "./logo-mark.svg",
  "./logo-mark.png",
  "./assets/hero-player.webp?v=2026-11-28-21",
  "./assets/rostok-logo.webp?v=2026-11-28-21",
  "./apple-touch-icon-v3-180.png",
  "./icon-v3-192.png",
  "./icon-v3-512.png",
  "./icon-maskable-v3-192.png",
  "./icon-maskable-v3-512.png",
];

async function precacheAll(cache, urls) {
  await Promise.all(
    urls.map(async (url) => {
      try {
        await cache.add(url);
      } catch (error) {
        console.warn("precache skip", url, error);
      }
    })
  );
}

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(STATIC).then((cache) => precacheAll(cache, PRECACHE)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys();
      await Promise.all(
        keys.filter((key) => key !== STATIC && key !== DATA).map((key) => caches.delete(key))
      );
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
  const freshCode = /\.(?:html|js|css)$/.test(url.pathname) || url.pathname.endsWith("/");
  if (/\/(?:data|news)\.json$/.test(url.pathname)) {
    event.respondWith(networkFirst(request, DATA));
    return;
  }
  if (freshCode) {
    event.respondWith(networkFirst(request, STATIC));
    return;
  }
  const pwaIcon =
    /\/icon(?:-maskable)?-v3-\d+\.png$/i.test(url.pathname) ||
    url.pathname.endsWith("/apple-touch-icon-v3-180.png") ||
    url.pathname.endsWith("/manifest.json");
  if (pwaIcon) {
    event.respondWith(networkFirst(request, STATIC));
    return;
  }
  event.respondWith(staleWhileRevalidate(event, request));
});

async function networkFirst(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);
  try {
    const fresh = await fetch(request);
    if (fresh && fresh.ok) {
      await cache.put(request, fresh.clone());
      return fresh;
    }
    if (cached) return cached;
    return fresh;
  } catch (error) {
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
