// Python<->JS routing parity check. Reads shared test vectors produced by
// `python -m scripts.export_parity_vectors` and asserts JS Dijkstra matches
// Python within tolerance. Runs with plain node (sandbox + CI core job).

import fs from "node:fs";
import assert from "node:assert";
import { buildGraph, dijkstra, CostMode } from "../src/routing.js";

const path = process.argv[2] || "../results/parity_vectors_SYNTHETIC.json";
if (!fs.existsSync(path)) {
  console.error(`parity vectors not found at ${path}; run: python -m scripts.export_parity_vectors`);
  process.exit(2);
}
const v = JSON.parse(fs.readFileSync(path, "utf-8"));
const g = buildGraph(v.graph);
let maxDiff = 0, n = 0, fails = 0;
for (const c of v.cases) {
  const mode = c.mode === "time" ? CostMode.TIME : CostMode.UNCERTAINTY;
  const r = dijkstra(g, c.s, c.t, mode);
  if (!r.found) { fails++; continue; }
  maxDiff = Math.max(maxDiff, Math.abs(r.cost - c.cost));
  n++;
}
console.log(`[parity] cases=${n} fails=${fails} maxCostDiff=${maxDiff}`);
assert.ok(fails === 0, "some JS routes not found");
assert.ok(maxDiff < 1e-6, `parity exceeded tolerance: ${maxDiff}`);
console.log("[parity] PY<->JS routing parity OK");
