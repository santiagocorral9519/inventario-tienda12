// Service worker: permite instalar la app y usarla sin conexión.
// App shell -> cache-first. catalogo.json -> network-first (siempre precios frescos si hay red).
const CACHE = "inv-t12-v1";
const SHELL = ["./", "index.html", "manifest.webmanifest", "icon.svg"];

self.addEventListener("install", e=>{
  e.waitUntil(caches.open(CACHE).then(c=>c.addAll(SHELL)).then(()=>self.skipWaiting()));
});
self.addEventListener("activate", e=>{
  e.waitUntil(caches.keys().then(ks=>Promise.all(ks.filter(k=>k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim()));
});
self.addEventListener("fetch", e=>{
  const url = new URL(e.request.url);
  if(url.pathname.endsWith("catalogo.json")){
    // network-first: intenta red, guarda copia, cae a cache si no hay conexion
    e.respondWith(
      fetch(e.request).then(res=>{
        const copy = res.clone();
        caches.open(CACHE).then(c=>c.put(e.request, copy));
        return res;
      }).catch(()=>caches.match(e.request))
    );
    return;
  }
  // resto: cache-first
  e.respondWith(caches.match(e.request).then(r=>r || fetch(e.request)));
});
