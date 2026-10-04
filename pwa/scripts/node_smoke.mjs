// Dependency-free smoke test for the offline logic modules. Runs with plain
// `node` (works in the sandbox and CI core job, no npm install needed).
// Exits non-zero on failure. Mirrors the Vitest assertions.

import assert from "node:assert";
import { haversineM, bearingDeg } from "../src/geo.js";
import { KDTree, isOutsideGraph } from "../src/snapping.js";
import { maneuver, isOffRoute } from "../src/turnbyturn.js";
import { survivalPenalty, buildGraph, dijkstra, CostMode } from "../src/routing.js";
import { t, setLang, availableLangs } from "../src/i18n.js";
import { queueSOS, pending, flush, _resetMem } from "../src/sync.js";

let n = 0;
const ok = (cond, msg) => { assert.ok(cond, msg); n++; };

ok(haversineM(0, 0, 1, 0) > 110000 && haversineM(0, 0, 1, 0) < 112000, "haversine");
ok(Math.abs(bearingDeg(0, 0, 1, 0)) < 1, "bearing north");
ok(new KDTree([{ id: 1, lat: 0, lon: 0 }, { id: 2, lat: 0, lon: 1 }]).nearest(0.1, 0.1).node.id === 1, "kdtree");
ok(isOutsideGraph(500) === true, "outside graph");
ok(maneuver(90) === "turn right" && maneuver(0) === "continue straight", "maneuver");
ok(isOffRoute(0.001, 0.005, [{ lat: 0, lon: 0 }, { lat: 0, lon: 0.01 }], 40) === true, "off-route");
ok(survivalPenalty(0) === 0 && survivalPenalty(0.9) > survivalPenalty(0.5), "survival penalty");

const g = buildGraph({
  nodes: [{ id: 0, lat: 0, lon: 0 }, { id: 1, lat: 0, lon: 0.01 }, { id: 2, lat: 0, lon: 0.02 }],
  edges: [{ id: 0, u: 0, v: 1, length_m: 100, speed_kph: 36 },
          { id: 1, u: 1, v: 2, length_m: 100, speed_kph: 36 }],
});
const r = dijkstra(g, 0, 2, CostMode.TIME);
ok(r.found && Math.abs(r.cost - 20) < 1e-6, "dijkstra tiny graph");

ok(availableLangs().length === 3, "i18n langs");
setLang("hi"); ok(t("sos").length > 0, "i18n hi"); setLang("en");

_resetMem();
await queueSOS({ id: "a", ts: 1 });
ok((await pending()).length === 1, "sync queue");
await flush(async () => true);
ok((await pending()).length === 0, "sync flush");

console.log(`[JS smoke] ${n} assertions passed`);
