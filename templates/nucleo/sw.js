/* Service worker: solo cachea recursos estáticos y una página sin conexión.
   Nunca guarda páginas con datos de clientes. */
const CACHE = "estudio-{{ version }}";
const RECURSOS = [{% for r in recursos %}"{{ r }}", {% endfor %}"/offline/"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(RECURSOS)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((claves) => Promise.all(claves.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (req.mode === "navigate") {
    e.respondWith(fetch(req).catch(() => caches.match("/offline/")));
    return;
  }
  if (url.pathname.startsWith("/static/")) {
    e.respondWith(caches.match(req).then((r) => r || fetch(req).then((resp) => {
      const copia = resp.clone();
      if (resp.ok) caches.open(CACHE).then((c) => c.put(req, copia));
      return resp;
    })));
  }
});
