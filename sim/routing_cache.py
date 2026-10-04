"""Per-episode routing cache for the simulator.

Computing a fresh route for every agent to every shelter is far too slow. Since
all agents in an episode share the same graph and cost field, we compute a
single multi-source shortest-path tree FROM ALL SHELTERS over the REVERSED graph
under the chosen cost mode. This yields, for every node, its cost-to-nearest
shelter and the next edge to take -- an O((V+E) log V) precomputation that all
agents then read in O(path length).

This is the standard "evacuation tree" / reverse-SSSP trick and keeps the
simulator fast enough for 30+ seeds x thousands of agents. Rerouting around a
discovered blockage still falls back to a local recompute, which is rare.
"""

from __future__ import annotations

import heapq
import math

from routing.costs import CostConfig, CostMode, edge_cost
from routing.graph import Graph


class ShelterTree:
    """Reverse multi-source Dijkstra from all shelters under a cost mode."""

    def __init__(self, graph: Graph, cost_mode: CostMode, blocked: set[int] | None = None):
        self.g = graph
        self.cfg = CostConfig(mode=cost_mode)
        self.blocked = blocked or set()
        self.dist: dict[int, float] = {}
        self.next_edge: dict[int, int] = {}   # node -> outgoing edge id toward shelter
        self.best_shelter: dict[int, int] = {}
        self._build()

    def _build(self) -> None:
        shelters = [n.id for n in self.g.nodes.values()
                    if n.is_shelter and n.shelter_capacity > 0]
        pq: list[tuple[float, int, int]] = []  # (dist, node, shelter)
        for s in shelters:
            self.dist[s] = 0.0
            self.best_shelter[s] = s
            heapq.heappush(pq, (0.0, s, s))
        while pq:
            d, u, sh = heapq.heappop(pq)
            if d > self.dist.get(u, math.inf):
                continue
            # relax reverse edges: for edge (w -> u), w can reach a shelter via u
            for e in self.g.in_edges(u):
                if e.id in self.blocked:
                    continue
                w = edge_cost(e, self.cfg)
                if math.isinf(w):
                    continue
                nd = d + w
                if nd < self.dist.get(e.u, math.inf):
                    self.dist[e.u] = nd
                    self.next_edge[e.u] = e.id
                    self.best_shelter[e.u] = sh
                    heapq.heappush(pq, (nd, e.u, sh))

    def route_from(self, source: int, avoid_shelters: set[int] | None = None
                   ) -> tuple[int | None, list[int]]:
        """Return (shelter, edge_id_path) following the precomputed tree.

        If `avoid_shelters` is given and the tree's target is in it, this falls
        back to None (caller does a local recompute to a different shelter)."""
        if source not in self.dist or math.isinf(self.dist[source]):
            return None, []
        edges: list[int] = []
        cur = source
        guard = 0
        while cur not in (self.best_shelter.get(cur),) and guard < self.g.n_nodes + 5:
            # stop when we've reached a shelter node (next_edge absent)
            eid = self.next_edge.get(cur)
            if eid is None:
                break
            edges.append(eid)
            cur = self.g.edges[eid].v
            guard += 1
            if self.g.nodes[cur].is_shelter:
                break
        shelter = cur if self.g.nodes[cur].is_shelter else self.best_shelter.get(source)
        if avoid_shelters and shelter in avoid_shelters:
            return None, []
        return shelter, edges
