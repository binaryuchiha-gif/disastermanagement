"""Dynamic rerouting when edges are reported blocked mid-trip (Phase 3, item 7).

Two strategies are compared:
  (a) Full recompute: re-run Dijkstra/A* from the current position each time an
      edge is reported blocked.
  (b) D* Lite: incremental shortest-path repair (Koenig & Likhachev, 2002) that
      reuses previous computation and only repairs the affected part of the
      search tree.

We implement a correct D* Lite over the current cost mode and provide a harness
that replays a sequence of blockages and records per-event latency and nodes
expanded, so Phase 4 can report D* Lite vs full-recompute latency.

Reference: S. Koenig and M. Likhachev, "D* Lite", AAAI 2002. (Standard
textbook algorithm; implemented from the published pseudocode.)
"""

from __future__ import annotations

import heapq
import math

from .costs import CostConfig, edge_cost
from .graph import Graph
from .shortest_path import PathResult, dijkstra


class DStarLite:
    """D* Lite searching from goal outward, re-planning as edges change.

    The agent sits at `start` and moves toward `goal`. When edges become blocked
    we call `update_edge_blocked` then `replan` to repair g-values and read off
    the next move. Costs come from the shared edge_cost model.
    """

    def __init__(self, graph: Graph, start: int, goal: int, cfg: CostConfig):
        self.g: Graph = graph
        self.start = start
        self.goal = goal
        self.cfg = cfg
        self.km = 0.0
        self.blocked: set[int] = set()  # blocked edge ids
        self.rhs: dict[int, float] = {}
        self.gval: dict[int, float] = {}
        self.U: list[tuple[tuple[float, float], int]] = []
        self._in_u: dict[int, tuple[float, float]] = {}
        self.expansions = 0
        self._init()

    # --- cost helpers (operate on the current cost mode, honouring blockages) ---
    def _cost(self, eid: int) -> float:
        if eid in self.blocked:
            return math.inf
        return edge_cost(self.g.edges[eid], self.cfg)

    def _succ_edges(self, n: int):
        return self.g.out_edges(n)

    def _pred_edges(self, n: int):
        return self.g.in_edges(n)

    def _h(self, a: int, b: int) -> float:
        # admissible heuristic consistent with edge_cost (lower bound on cost)
        sld = self.g.straight_line_m(a, b)
        vmax = max((e.speed_kph for e in self.g.edges.values()), default=1.0)
        return sld / (vmax * 1000.0 / 3600.0)

    def _key(self, n: int) -> tuple[float, float]:
        k2 = min(self.gval.get(n, math.inf), self.rhs.get(n, math.inf))
        k1 = k2 + self._h(self.start, n) + self.km
        return (k1, k2)

    def _init(self) -> None:
        for n in self.g.nodes:
            self.gval[n] = math.inf
            self.rhs[n] = math.inf
        self.rhs[self.goal] = 0.0
        self._u_insert(self.goal, self._key(self.goal))
        self.replan()

    def _u_insert(self, n: int, k) -> None:
        self._in_u[n] = k
        heapq.heappush(self.U, (k, n))

    def _u_update(self, n: int, k) -> None:
        self._in_u[n] = k
        heapq.heappush(self.U, (k, n))

    def _u_remove(self, n: int) -> None:
        self._in_u.pop(n, None)

    def _u_top(self):
        while self.U:
            k, n = self.U[0]
            cur = self._in_u.get(n)
            if cur is None or cur != k:
                heapq.heappop(self.U)  # stale entry
                continue
            return k, n
        return None, None

    def _update_vertex(self, u: int) -> None:
        if u != self.goal:
            best = math.inf
            for e in self._succ_edges(u):
                best = min(best, self._cost(e.id) + self.gval.get(e.v, math.inf))
            self.rhs[u] = best
        self._u_remove(u)
        if self.gval.get(u, math.inf) != self.rhs.get(u, math.inf):
            self._u_insert(u, self._key(u))

    def replan(self) -> None:
        while True:
            k, u = self._u_top()
            if u is None:
                break
            if not (k < self._key(self.start) or
                    self.rhs.get(self.start, math.inf) != self.gval.get(self.start, math.inf)):
                break
            self.expansions += 1
            heapq.heappop(self.U)
            self._in_u.pop(u, None)
            k_new = self._key(u)
            if k < k_new:
                self._u_insert(u, k_new)
            elif self.gval.get(u, math.inf) > self.rhs.get(u, math.inf):
                self.gval[u] = self.rhs[u]
                for e in self._pred_edges(u):
                    self._update_vertex(e.u)
            else:
                self.gval[u] = math.inf
                self._update_vertex(u)
                for e in self._pred_edges(u):
                    self._update_vertex(e.u)

    def update_edge_blocked(self, edge_id: int) -> None:
        """Mark an edge blocked and repair affected vertices."""
        if edge_id in self.blocked:
            return
        self.blocked.add(edge_id)
        e = self.g.edges[edge_id]
        # recompute km with heuristic shift relative to current start
        self._update_vertex(e.u)
        self.replan()

    def set_start(self, new_start: int) -> None:
        """Move the agent; D* Lite shifts km by the heuristic between old/new."""
        self.km += self._h(self.start, new_start)
        self.start = new_start

    def extract_path(self) -> PathResult:
        """Greedily follow min g-value successors from start to goal."""
        if math.isinf(self.gval.get(self.start, math.inf)):
            return PathResult([], [], math.inf, False, self.expansions)
        nodes = [self.start]
        edges: list[int] = []
        cur = self.start
        total = 0.0
        guard = 0
        while cur != self.goal and guard < self.g.n_nodes + 5:
            guard += 1
            best_e, best_val = None, math.inf
            for e in self._succ_edges(cur):
                val = self._cost(e.id) + self.gval.get(e.v, math.inf)
                if val < best_val:
                    best_val, best_e = val, e
            if best_e is None or math.isinf(best_val):
                return PathResult([], [], math.inf, False, self.expansions)
            total += self._cost(best_e.id)
            edges.append(best_e.id)
            cur = best_e.v
            nodes.append(cur)
        found = cur == self.goal
        return PathResult(nodes, edges, total if found else math.inf, found, self.expansions)


def full_recompute(graph: Graph, start: int, goal: int, cfg: CostConfig,
                   blocked: set[int]) -> PathResult:
    """Baseline: Dijkstra ignoring blocked edges (treated as inf)."""
    # temporarily reflect blockages via a wrapper cost
    orig = {}
    for eid in blocked:
        orig[eid] = graph.edges[eid].p_fail
        graph.edges[eid].p_fail = 1.0  # effectively infinite survival penalty
    try:
        # use a very high beta to make blocked edges unusable under any mode
        from .costs import CostMode
        if cfg.mode in (CostMode.TIME, CostMode.DISTANCE):
            # for pure time/distance, blocked edges must be skipped explicitly
            return _dijkstra_skip(graph, start, goal, cfg, blocked)
        return dijkstra(graph, start, goal, cfg)
    finally:
        for eid, p in orig.items():
            graph.edges[eid].p_fail = p


def _dijkstra_skip(graph, source, target, cfg, blocked):
    dist = {source: 0.0}
    prev_node, prev_edge = {}, {}
    pq = [(0.0, source)]
    settled = set()
    expanded = 0
    while pq:
        d, u = heapq.heappop(pq)
        if u in settled:
            continue
        settled.add(u)
        expanded += 1
        if u == target:
            from .shortest_path import _reconstruct
            nodes, edges = _reconstruct(prev_node, prev_edge, source, target)
            return PathResult(nodes, edges, d, True, expanded)
        for e in graph.out_edges(u):
            if e.id in blocked:
                continue
            w = edge_cost(e, cfg)
            if math.isinf(w):
                continue
            nd = d + w
            if nd < dist.get(e.v, math.inf):
                dist[e.v] = nd
                prev_node[e.v] = u
                prev_edge[e.v] = e.id
                heapq.heappush(pq, (nd, e.v))
    return PathResult([], [], math.inf, False, expanded)
