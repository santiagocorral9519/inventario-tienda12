// Service worker: instala la app y permite usarla sin conexion.
// index.html y catalogo.json -> network-first (siempre fresco si hay red, cae a cache offline).
//   asi cualquier actualizacion de la app llega sola al abrirla con internet.
// Resto del shell (manifest, icon) -> cache-first.
const CACHE = "inv-t12-v2";
const SHELL = ["./", "index.html", "manifest.webmanifest", "icon.svg"];

self.addEventListener("install", e=>{
  e.waitUntil(caches.open(CACHE).then(c=>c.addAll(SHELL)).then(()=>self.skipWaiting()));
});
self.addEventListener("activate", e=>{
  e.waitUntil(caches.keys().then(ks=>Promise.all(ks.filter(k=>k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim()));
});

self.addEventListener("fetch", e=>{
  const url = new URL(e.request.url);
  // abrir la app / index.html -> red primero, cache si no hay conexion
  if(e.request.mode === "navigate" || url.pathname.endsWith("index.html")){
    e.respondWith(
      fetch(e.request).then(res=>{
        const copy = res.clone(); caches.open(CACHE).then(c=>c.put(e.request, copy));
        return res;
      }).catch(()=> caches.match(e.request).then(r=> r || caches.match("index.html")))
    );
    return;
  }
  // precios -> red primero, cache si no hay conexion
  if(url.pathname.endsWith("catalogo.json")){
    e.respondWith(
      fetch(e.request).then(res=>{
        const copy = res.clone(); caches.open(CACHE).then(c=>c.put(e.request, copy));
        return res;
      }).catch(()=> caches.match(e.request))
    );
    return;
  }
  // resto: cache-first
  e.respondWith(caches.match(e.request).then(r=> r || fetch(e.request)));
});
