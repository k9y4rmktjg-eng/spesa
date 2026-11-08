// Funzionamento offline: app sempre disponibile, offerte e foto in cache.
const V = "spesa-v4";
const SHELL = ["./", "index.html", "config.js", "manifest.webmanifest", "icons/icon-192.png", "icons/apple-touch-icon.png"];
self.addEventListener("install", e => { e.waitUntil(caches.open(V).then(c => c.addAll(SHELL))); self.skipWaiting(); });
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(k => Promise.all(k.filter(x => x !== V && x !== "foto").map(x => caches.delete(x)))));
  self.clients.claim();
});
self.addEventListener("fetch", e => {
  const r = e.request, u = new URL(r.url);
  if (r.method !== "GET") return;
  if (u.hostname.includes("firestore") || u.hostname.includes("googleapis.com") && u.pathname.includes("Listen")) return;
  // foto prodotti: prima la cache
  if (r.destination === "image" && u.origin !== location.origin || u.pathname.includes("/data/img/")) {
    e.respondWith(caches.open("foto").then(async c => {
      const hit = await c.match(r); if (hit) return hit;
      try { const res = await fetch(r); if (res.ok || res.type === "opaque") c.put(r, res.clone()); return res; }
      catch { return new Response("", { status: 404 }); }
    }));
    return;
  }
  // tutto il resto dell'app: prima la rete, poi la cache
  if (u.origin === location.origin || u.hostname.includes("gstatic.com") || u.hostname.includes("fonts.")) {
    e.respondWith(fetch(r).then(res => {
      if (res.ok) { const cl = res.clone(); caches.open(V).then(c => c.put(r.url.split("?")[0], cl)); }
      return res;
    }).catch(() => caches.match(r.url.split("?")[0]).then(x => x || caches.match("index.html"))));
  }
});
