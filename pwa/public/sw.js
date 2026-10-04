// ResQFlow-X service worker: offline-first caching + HTTP Range support for the
// PMTiles basemap. PMTiles requests the single .pmtiles file via byte ranges;
// the Cache API stores whole responses, so we cache the full file once and then
// answer Range requests by slicing the cached body ourselves. This is THE most
// common offline-maps failure point, so it is handled explicitly here.

const CACHE = "resqflow-x-v1";
const CORE_ASSETS = [
  "/",
  "/index.html",
  "/style-muted.json",
  "/src/main.js",
  "/src/geo.js",
  "/src/routing.js",
  "/src/snapping.js",
  "/src/turnbyturn.js",
  "/src/risk_model_SYNTHETIC.js",
  "/fonts/", // glyph PBFs (self-hosted)
  "/sprites/", // sprite sheet (self-hosted)
];
const MAP_FILE = "/tiles/study_area_SYNTHETIC.pmtiles";

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(CORE_ASSETS.filter((u) => !u.endsWith("/")))),
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))),
    ),
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (url.pathname.endsWith(".pmtiles")) {
    event.respondWith(handlePmtiles(event.request));
    return;
  }
  // cache-first for everything else (offline-first)
  event.respondWith(
    caches.match(event.request).then((hit) => hit || fetchAndCache(event.request)),
  );
});

async function fetchAndCache(request) {
  try {
    const resp = await fetch(request);
    if (resp.ok && request.method === "GET") {
      const cache = await caches.open(CACHE);
      cache.put(request, resp.clone());
    }
    return resp;
  } catch (e) {
    // offline and uncached: fall back to a minimal response for navigations
    if (request.mode === "navigate") return caches.match("/index.html");
    throw e;
  }
}

// Answer Range requests for the PMTiles file from a single cached full copy.
async function handlePmtiles(request) {
  const cache = await caches.open(CACHE);
  let full = await cache.match(MAP_FILE);
  if (!full) {
    // first load: fetch the whole file (progress is shown by the download flow)
    try {
      const resp = await fetch(MAP_FILE);
      if (!resp.ok) throw new Error("pmtiles fetch failed");
      await cache.put(MAP_FILE, resp.clone());
      full = await cache.match(MAP_FILE);
    } catch (e) {
      return new Response("PMTiles unavailable offline", { status: 503 });
    }
  }
  const range = request.headers.get("range");
  const buf = await full.arrayBuffer();
  if (!range) {
    return new Response(buf, {
      status: 200,
      headers: { "Content-Type": "application/octet-stream",
                 "Content-Length": String(buf.byteLength),
                 "Accept-Ranges": "bytes" },
    });
  }
  // parse "bytes=start-end"
  const m = /bytes=(\d+)-(\d*)/.exec(range);
  const start = parseInt(m[1], 10);
  const end = m[2] ? parseInt(m[2], 10) : buf.byteLength - 1;
  const sliced = buf.slice(start, end + 1);
  return new Response(sliced, {
    status: 206,
    headers: {
      "Content-Type": "application/octet-stream",
      "Content-Range": `bytes ${start}-${end}/${buf.byteLength}`,
      "Content-Length": String(sliced.byteLength),
      "Accept-Ranges": "bytes",
    },
  });
}
