"""Dijkstra and A* shortest-path over a Graph with pluggable edge costs.

Algorithms 1-4 of Phase 3 are all realized here: by choosing CostConfig.mode
you get shortest-distance (baseline 1), shortest-time, static-risk (baseline 3),
or uncertainty-aware / UCB routing (item 4). A* (item 2) uses an admissible
heuristic; admissibility is argued below and property-tested in tests/.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass

from .costs import CostConfig, CostMode, edge_cost
from .graph import Graph


@dataclass
class PathResult:
    nodes: list[int]
    edges: list[int]
    cost: float            # total cost in the chosen cost mode
    found: bool
    expanded: int = 0      # number of settled nodes (for benchmarking A* vs Dijkstra)

    @property
    def is_empty(self) -> bool:
        return not self.found


def _reconstruct(prev_node, prev_edge, source, target) -> tuple[list[int], list[int]]:
    nodes = [target]
    edges: list[int] = []
    cur = target
    while cur != source:
        e = prev_edge[cur]
        edges.append(e)
        cur = prev_node[cur]
        nodes.append(cur)
    nodes.reverse()
    edges.reverse()
    return nodes, edges


def dijkstra(graph: Graph, source: int, target: int, cfg: CostConfig) -> PathResult:
    """Standard Dijkstra. Requires nonnegative edge costs (guaranteed by costs.py
    except math.inf, which simply means 'blocked')."""
    dist: dict[int, float] = {source: 0.0}
    prev_node: dict[int, int] = {}
    prev_edge: dict[int, int] = {}
    pq: list[tuple[float, int]] = [(0.0, source)]
    settled: set[int] = set()
    expanded = 0

    while pq:
        d, u = heapq.heappop(pq)
        if u in settled:
            continue
        settled.add(u)
        expanded += 1
        if u == target:
            nodes, edges = _reconstruct(prev_node, prev_edge, source, target)
            return PathResult(nodes, edges, d, True, expanded)
        for e in graph.out_edges(u):
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


def _heuristic(graph: Graph, node: int, target: int, cfg: CostConfig) -> float:
    """Admissible heuristic h(n) = a provable lower bound on remaining cost.

    - DISTANCE: straight-line (haversine) distance <= any road distance. Admissible.
    - TIME / risk / uncertainty: straight-line distance divided by the GLOBAL max
      speed gives a lower bound on remaining travel time, and all risk/uncertainty
      penalties are nonnegative, so this never overestimates the true remaining
      cost. Admissible (and consistent).
    """
    sld = graph.straight_line_m(node, target)
    if cfg.mode == CostMode.DISTANCE:
        return sld
    vmax_kph = _max_speed(graph)
    return sld / (vmax_kph * 1000.0 / 3600.0)


_MAXSPEED_CACHE: dict[int, float] = {}


def _max_speed(graph: Graph) -> float:
    key = id(graph)
    v = _MAXSPEED_CACHE.get(key)
    if v is None:
        v = max((e.speed_kph for e in graph.edges.values()), default=1.0)
        _MAXSPEED_CACHE[key] = v
    return max(v, 1e-3)


def astar(graph: Graph, source: int, target: int, cfg: CostConfig) -> PathResult:
    """A* with an admissible, consistent heuristic (see _heuristic)."""
    g_score: dict[int, float] = {source: 0.0}
    prev_node: dict[int, int] = {}
    prev_edge: dict[int, int] = {}
    h0 = _heuristic(graph, source, target, cfg)
    pq: list[tuple[float, int]] = [(h0, source)]
    settled: set[int] = set()
    expanded = 0

    while pq:
        _, u = heapq.heappop(pq)
        if u in settled:
            continue
        settled.add(u)
        expanded += 1
        if u == target:
            nodes, edges = _reconstruct(prev_node, prev_edge, source, target)
            return PathResult(nodes, edges, g_score[u], True, expanded)
        du = g_score[u]
        for e in graph.out_edges(u):
            w = edge_cost(e, cfg)
            if math.isinf(w):
                continue
            ng = du + w
            if ng < g_score.get(e.v, math.inf):
                g_score[e.v] = ng
                prev_node[e.v] = u
                prev_edge[e.v] = e.id
                f = ng + _heuristic(graph, e.v, target, cfg)
                heapq.heappush(pq, (f, e.v))
    return PathResult([], [], math.inf, False, expanded)


def path_metrics(graph: Graph, result: PathResult) -> dict:
    """Compute descriptive metrics for a found path: total time, distance,
    product survival probability, and max single-edge failure probability."""
    if result.is_empty:
        return {"time_s": math.inf, "distance_m": math.inf,
                "survival_prob": 0.0, "max_edge_pfail": 1.0, "block_prob": 1.0}
    t = d = 0.0
    surv = 1.0
    maxp = 0.0
    for eid in result.edges:
        e = graph.edges[eid]
        t += e.free_flow_time_s
        d += e.length_m
        surv *= (1.0 - min(max(e.p_fail, 0.0), 1.0))
        maxp = max(maxp, e.p_fail)
    return {"time_s": t, "distance_m": d, "survival_prob": surv,
            "max_edge_pfail": maxp, "block_prob": 1.0 - surv}
