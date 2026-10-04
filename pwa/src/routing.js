// On-device routing (Dijkstra + uncertainty-aware cost), pure JS. Shares the
// cost model and test vectors with the Python routing library (parity-tested in
// tests/test_js_routing_parity via a shared JSON graph + expected costs).

const SURV_CAP = 25.0;
const EPS = 1e-9;

export function survivalPenalty(pFail) {
  const p = Math.min(Math.max(pFail, 0), 1 - EPS);
  return Math.min(SURV_CAP, -Math.log(1 - p));
}

export const CostMode = {
  TIME: "time",
  DISTANCE: "distance",
  STATIC_RISK: "static_risk",
  UNCERTAINTY: "uncertainty",
  UNCERTAINTY_UCB: "uncertainty_ucb",
};

export function edgeCost(e, mode, lam = 300, beta = 300) {
  switch (mode) {
    case CostMode.DISTANCE: return e.length_m;
    case CostMode.TIME: return e.free_flow_time_s;
    case CostMode.STATIC_RISK: return e.free_flow_time_s + lam * (e.static_risk || 0);
    case CostMode.UNCERTAINTY: return e.free_flow_time_s + beta * survivalPenalty(e.p_fail || 0);
    case CostMode.UNCERTAINTY_UCB:
      return e.free_flow_time_s + beta * survivalPenalty(e.p_fail_hi || e.p_fail || 0);
    default: throw new Error("unknown cost mode " + mode);
  }
}

// Binary-heap-free Dijkstra using a simple array PQ is O(V^2); for city graphs
// we use a binary heap for parity with Python performance characteristics.
class MinHeap {
  constructor() { this.a = []; }
  push(item) { const a = this.a; a.push(item); let i = a.length - 1;
    while (i > 0) { const p = (i - 1) >> 1; if (a[p][0] <= a[i][0]) break;
      [a[p], a[i]] = [a[i], a[p]]; i = p; } }
  pop() { const a = this.a; const top = a[0]; const last = a.pop();
    if (a.length) { a[0] = last; let i = 0;
      for (;;) { const l = 2 * i + 1, r = 2 * i + 2; let m = i;
        if (l < a.length && a[l][0] < a[m][0]) m = l;
        if (r < a.length && a[r][0] < a[m][0]) m = r;
        if (m === i) break; [a[m], a[i]] = [a[i], a[m]]; i = m; } }
    return top; }
  get size() { return this.a.length; }
}

// graph: { nodes: Map(id->node), adj: Map(id->[edges]) }
export function dijkstra(graph, source, target, mode = CostMode.UNCERTAINTY) {
  const dist = new Map([[source, 0]]);
  const prevNode = new Map();
  const prevEdge = new Map();
  const settled = new Set();
  const pq = new MinHeap();
  pq.push([0, source]);
  let expanded = 0;
  while (pq.size) {
    const [d, u] = pq.pop();
    if (settled.has(u)) continue;
    settled.add(u); expanded++;
    if (u === target) {
      const nodes = [target]; const edges = []; let cur = target;
      while (cur !== source) { edges.push(prevEdge.get(cur)); cur = prevNode.get(cur); nodes.push(cur); }
      nodes.reverse(); edges.reverse();
      return { nodes, edges, cost: d, found: true, expanded };
    }
    for (const e of graph.adj.get(u) || []) {
      const w = edgeCost(e, mode);
      if (!isFinite(w)) continue;
      const nd = d + w;
      if (nd < (dist.has(e.v) ? dist.get(e.v) : Infinity)) {
        dist.set(e.v, nd); prevNode.set(e.v, u); prevEdge.set(e.v, e.id);
        pq.push([nd, e.v]);
      }
    }
  }
  return { nodes: [], edges: [], cost: Infinity, found: false, expanded };
}

export function buildGraph(data) {
  const nodes = new Map();
  for (const n of data.nodes) nodes.set(n.id, n);
  const adj = new Map();
  for (const n of data.nodes) adj.set(n.id, []);
  for (const e of data.edges) {
    if (!e.free_flow_time_s) {
      const spd = Math.max(1e-3, e.speed_kph || 30);
      e.free_flow_time_s = e.length_m / ((spd * 1000) / 3600);
    }
    adj.get(e.u).push(e);
  }
  return { nodes, adj };
}
