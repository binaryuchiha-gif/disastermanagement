// Vitest unit tests for the offline logic modules. Run with `npm run test`.
// (UNVERIFIED in the dev sandbox — npm install is blocked — but the same
// assertions are exercised by scripts/node_smoke.mjs with plain node, which
// DOES run in the sandbox and in CI's core job.)

import { describe, it, expect } from "vitest";
import { haversineM, bearingDeg, pointToSegmentM } from "../src/geo.js";
import { KDTree, snapToEdge, isOutsideGraph } from "../src/snapping.js";
import { buildInstructions, maneuver, isOffRoute, deviationM } from "../src/turnbyturn.js";
import { survivalPenalty, edgeCost, CostMode, buildGraph, dijkstra } from "../src/routing.js";
import { t, setLang, availableLangs } from "../src/i18n.js";
import { queueSOS, queueReport, pending, flush, resolveConflict, _resetMem } from "../src/sync.js";

describe("geo", () => {
  it("haversine ~111km per degree latitude", () => {
    expect(haversineM(0, 0, 1, 0)).toBeGreaterThan(110000);
    expect(haversineM(0, 0, 1, 0)).toBeLessThan(112000);
  });
  it("bearing north is ~0", () => expect(bearingDeg(0, 0, 1, 0)).toBeCloseTo(0, 0));
  it("point on segment has zero distance", () => {
    const { dist } = pointToSegmentM(0, 0.5, 0, 0, 0, 1);
    expect(dist).toBeLessThan(1);
  });
});

describe("snapping", () => {
  const nodes = [{ id: 1, lat: 0, lon: 0 }, { id: 2, lat: 0, lon: 0.01 }, { id: 3, lat: 0.01, lon: 0 }];
  it("kdtree finds nearest node", () => {
    const kd = new KDTree(nodes);
    expect(kd.nearest(0.0001, 0.0001).node.id).toBe(1);
  });
  it("detects outside graph", () => expect(isOutsideGraph(500)).toBe(true));
});

describe("turn-by-turn", () => {
  it("classifies maneuvers", () => {
    expect(maneuver(0)).toBe("continue straight");
    expect(maneuver(90)).toBe("turn right");
    expect(maneuver(-90)).toBe("turn left");
  });
  it("builds instructions ending at destination", () => {
    const steps = buildInstructions([{ lat: 0, lon: 0 }, { lat: 0, lon: 0.01 }, { lat: 0.01, lon: 0.01 }]);
    expect(steps[steps.length - 1].instruction).toMatch(/Arrive/);
  });
  it("off-route detection", () => {
    const route = [{ lat: 0, lon: 0 }, { lat: 0, lon: 0.01 }];
    expect(isOffRoute(0.001, 0.005, route, 40)).toBe(true);  // ~110m off
    expect(isOffRoute(0.0, 0.005, route, 40)).toBe(false);
  });
});

describe("routing", () => {
  it("survival penalty 0 at p=0, increasing", () => {
    expect(survivalPenalty(0)).toBe(0);
    expect(survivalPenalty(0.9)).toBeGreaterThan(survivalPenalty(0.5));
  });
  it("dijkstra finds a route on a tiny graph", () => {
    const g = buildGraph({
      nodes: [{ id: 0, lat: 0, lon: 0 }, { id: 1, lat: 0, lon: 0.01 }, { id: 2, lat: 0, lon: 0.02 }],
      edges: [{ id: 0, u: 0, v: 1, length_m: 100, speed_kph: 36 },
              { id: 1, u: 1, v: 2, length_m: 100, speed_kph: 36 }],
    });
    const r = dijkstra(g, 0, 2, CostMode.TIME);
    expect(r.found).toBe(true);
    expect(r.cost).toBeCloseTo(20, 5);
  });
});

describe("i18n", () => {
  it("has three languages", () => expect(availableLangs()).toEqual(["en", "ta", "hi"]));
  it("falls back to en for missing keys", () => { setLang("ta"); expect(t("sos")).toBeTruthy(); setLang("en"); });
});

describe("sync", () => {
  it("queues and lists pending idempotently", async () => {
    _resetMem();
    await queueSOS({ id: "a", ts: 1 });
    await queueReport({ id: "b", ts: 2 });
    expect((await pending()).length).toBe(2);
  });
  it("flush marks items sent", async () => {
    _resetMem();
    await queueSOS({ id: "a", ts: 1 });
    const res = await flush(async () => true);
    expect(res[0].ok).toBe(true);
    expect((await pending()).length).toBe(0);
  });
  it("last-writer-wins conflict", () => {
    expect(resolveConflict({ ts: 2 }, { ts: 1 }).ts).toBe(2);
    expect(resolveConflict({ ts: 1 }, { ts: 5 }).ts).toBe(5);
  });
});
