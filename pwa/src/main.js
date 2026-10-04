// ResQFlow-X PWA entry point. UNVERIFIED in the sandbox (needs `npm install` +
// a browser). The offline *logic* modules it imports (geo, routing, snapping,
// turnbyturn, risk model) ARE unit-tested with node. This file wires them to
// MapLibre + PMTiles and the UI.

import maplibregl from "maplibre-gl";
import { Protocol } from "pmtiles";
import { predictProba, FEATURES } from "./risk_model_SYNTHETIC.js";
import { buildGraph, dijkstra, CostMode } from "./routing.js";
import { KDTree, snapToEdge, isOutsideGraph } from "./snapping.js";
import { buildInstructions, isOffRoute } from "./turnbyturn.js";
import { haversineM } from "./geo.js";

const SCENARIOS = ["mild", "moderate", "extreme"];
const RAIN = { mild: 0.25, moderate: 0.55, extreme: 0.9 };
const statusEl = document.getElementById("status");
const setStatus = (s) => (statusEl.textContent = s);

// --- register service worker (offline-first + PMTiles range handling) ---
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => setStatus("SW failed"));
}

// --- PMTiles protocol ---
const protocol = new Protocol();
maplibregl.addProtocol("pmtiles", protocol.tile);

let graph = null;
let kdtree = null;
let edgeGeom = [];
let start = null, dest = null;

async function loadGraph() {
  // compact SYNTHETIC graph shipped with the app
  const resp = await fetch("/data/synthetic_city_SEED1234.json");
  const data = await resp.json();
  graph = buildGraph(data);
  kdtree = new KDTree(data.nodes);
  const byId = new Map(data.nodes.map((n) => [n.id, n]));
  edgeGeom = data.edges.map((e) => ({
    id: e.id, u: e.u, v: e.v,
    ulat: byId.get(e.u).lat, ulon: byId.get(e.u).lon,
    vlat: byId.get(e.v).lat, vlon: byId.get(e.v).lon,
  }));
  return data;
}

// --- apply the on-device risk model to color edges for the current scenario ---
function scoreEdges(data, scenario) {
  const rain = RAIN[scenario];
  const features = {}; // edge_id -> feature vector (precomputed server-side ideally)
  // The compact graph ships precomputed terrain features per edge in e.feat.
  const fc = data.edges;
  for (const e of fc) {
    const f = e.feat || {};
    const x = [
      f.inv_elev_norm ?? 0, f.inv_slope_norm ?? 0, f.twi_norm ?? 0,
      f.flow_acc_norm ?? 0, f.near_water_norm ?? 0, f.hand_norm ?? 0,
      f.bridge_flag ?? 0, f.road_primary ?? 0, rain,
    ];
    e.p_fail = predictProba(x);
    graph.adj.get(e.u)?.forEach((ge) => { if (ge.id === e.id) ge.p_fail = e.p_fail; });
  }
}

function riskColorExpression() {
  return [
    "interpolate", ["linear"], ["get", "p_fail"],
    0.0, "#2ca02c", 0.4, "#f4a259", 0.8, "#d1495b",
  ];
}

async function main() {
  setStatus("loading map…");
  let style = "/style-muted.json";
  try {
    const data = await loadGraph();

    const map = new maplibregl.Map({
      container: "map",
      style,
      center: [80.2, 12.96],
      zoom: 12,
      maxZoom: 15,
    });
    map.addControl(new maplibregl.GeolocateControl({
      positionOptions: { enableHighAccuracy: true },
      trackUserLocation: true, showUserHeading: true,
    }));

    map.on("load", () => {
      setStatus("map ready (offline-capable)");
      addRiskLayer(map, data);
      wireScenario(map, data);
      wireRouting(map);
      wireSOS();
      wireDownload();
    });

    map.on("error", () => setStatus("tiles missing — using fallback style"));
  } catch (e) {
    setStatus("offline fallback: minimal style");
    renderFallback();
  }
}

function addRiskLayer(map, data) {
  scoreEdges(data, "moderate");
  const fc = {
    type: "FeatureCollection",
    features: edgeGeom.map((e) => ({
      type: "Feature",
      properties: { id: e.id, p_fail: (graph.adj.get(e.u).find((g) => g.id === e.id) || {}).p_fail || 0 },
      geometry: { type: "LineString", coordinates: [[e.ulon, e.ulat], [e.vlon, e.vlat]] },
    })),
  };
  if (map.getSource("risk")) map.getSource("risk").setData(fc);
  else {
    map.addSource("risk", { type: "geojson", data: fc });
    map.addLayer({ id: "risk-edges", type: "line", source: "risk",
      paint: { "line-color": riskColorExpression(), "line-width": 2.5, "line-opacity": 0.8 } });
  }
}

function wireScenario(map, data) {
  const slider = document.getElementById("scenario");
  const label = document.getElementById("scenarioLabel");
  slider.addEventListener("input", () => {
    const sc = SCENARIOS[parseInt(slider.value, 10)];
    label.textContent = sc;
    scoreEdges(data, sc);              // re-score on-device, zero network
    addRiskLayer(map, data);
    if (start && dest) computeRoute(map);
  });
}

function wireRouting(map) {
  const method = document.getElementById("method");
  map.on("click", (ev) => {
    const { lat, lng } = ev.lngLat;
    const snapNode = kdtree.nearest(lat, lng);
    if (isOutsideGraph(snapNode.dist)) { setStatus("tap is outside the road network"); return; }
    if (!start) { start = snapNode.node.id; setStatus("start set — tap destination"); }
    else { dest = snapNode.node.id; computeRoute(map); }
  });
  method.addEventListener("change", () => { if (start && dest) computeRoute(map); });
}

function computeRoute(map) {
  const method = document.getElementById("method").value;
  const mode = method === "astar_time" ? CostMode.TIME : CostMode.UNCERTAINTY;
  const t0 = performance.now();
  const res = dijkstra(graph, start, dest, mode);
  const ms = (performance.now() - t0).toFixed(1);
  if (!res.found) { setStatus("no route found"); return; }
  drawRoute(map, res);
  explain(res, ms);
}

function drawRoute(map, res) {
  const coords = [];
  for (const eid of res.edges) {
    const e = edgeGeom.find((g) => g.id === eid);
    coords.push([e.ulon, e.ulat], [e.vlon, e.vlat]);
  }
  const fc = { type: "Feature", geometry: { type: "LineString", coordinates: coords } };
  if (map.getSource("route")) map.getSource("route").setData(fc);
  else {
    map.addSource("route", { type: "geojson", data: fc });
    map.addLayer({ id: "route-line", type: "line", source: "route",
      paint: { "line-color": "#1f77b4", "line-width": 5, "line-opacity": 0.9 } });
  }
}

function explain(res, ms) {
  let meanP = 0;
  for (const eid of res.edges) {
    const e = edgeGeom.find((g) => g.id === eid);
    const ge = graph.adj.get(e.u).find((g) => g.id === eid);
    meanP += (ge.p_fail || 0);
  }
  meanP = res.edges.length ? meanP / res.edges.length : 0;
  document.getElementById("whyPanel").textContent =
    `Why this route: ${res.edges.length} segments, mean failure risk ${(meanP * 100).toFixed(0)}%, computed in ${ms} ms on-device.`;
}

function wireSOS() {
  document.getElementById("sos").addEventListener("click", async () => {
    const payload = await buildSOS();
    const { queueSOS } = await import("./sync.js");
    await queueSOS(payload);
    setStatus("SOS queued (will send when online)");
  });
}

async function buildSOS() {
  // compact <200 byte payload: location, battery, group size, timestamp
  let battery = null;
  try { const b = await navigator.getBattery?.(); battery = b ? Math.round(b.level * 100) : null; } catch {}
  const pos = await new Promise((res) =>
    navigator.geolocation?.getCurrentPosition(
      (p) => res(p.coords), () => res(null), { timeout: 3000 }) || res(null));
  return {
    id: crypto.randomUUID(),
    lat: pos ? +pos.latitude.toFixed(5) : null,
    lon: pos ? +pos.longitude.toFixed(5) : null,
    batt: battery, grp: 1, ts: Date.now(),
  };
}

function wireDownload() {
  document.getElementById("downloadMap").addEventListener("click", async () => {
    try {
      const est = await navigator.storage?.estimate?.();
      if (est) setStatus(`storage: ${(est.usage / 1e6) | 0}/${(est.quota / 1e6) | 0} MB`);
      const resp = await fetch("/tiles/study_area_SYNTHETIC.pmtiles");
      const total = +resp.headers.get("content-length") || 0;
      const reader = resp.body.getReader();
      let received = 0;
      const chunks = [];
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        chunks.push(value); received += value.length;
        if (total) setStatus(`downloading map… ${((received / total) * 100) | 0}%`);
      }
      const cache = await caches.open("resqflow-x-v1");
      await cache.put("/tiles/study_area_SYNTHETIC.pmtiles",
        new Response(new Blob(chunks), { headers: { "Content-Type": "application/octet-stream" } }));
      setStatus("offline map downloaded ✓");
    } catch (e) {
      setStatus("download failed — retry when online");
    }
  });
  document.getElementById("toggleContrast").addEventListener("click", (e) => {
    document.getElementById("map").classList.toggle("hi-contrast");
    const on = e.target.getAttribute("aria-pressed") === "true";
    e.target.setAttribute("aria-pressed", String(!on));
  });
}

function renderFallback() {
  const el = document.getElementById("map");
  el.innerHTML = '<div style="padding:20px">Offline minimal mode: routing & SOS available; basemap tiles missing. Tap "Download offline map" when online.</div>';
}

main();
