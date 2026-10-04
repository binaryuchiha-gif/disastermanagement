"""Multi-evacuee shelter assignment with capacities and congestion
(Phase 3, item 8).

Two layers:

1. min_cost_max_flow: a successive-shortest-path (SPFA/Bellman-Ford-based)
   min-cost max-flow. Used to assign evacuees from sources to shelters while
   respecting shelter capacities, minimising total routing cost. Flow
   conservation and capacity constraints are guaranteed by construction and
   property-tested.

2. msa_assignment: congestion-aware assignment. Edge travel time rises with
   load via the BPR (Bureau of Public Roads) function
       t(x) = t0 * (1 + a * (x / c)^b)
   and we solve a user-equilibrium-style problem with the Method of Successive
   Averages (MSA): iteratively route everyone on shortest paths at current
   times, then average the flow with the previous iterate (step 1/k). MSA is a
   standard, convergent, parameter-free alternative to Frank-Wolfe and needs no
   line search, which keeps it explainable for the viva.

Everything is pure stdlib.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field

from .costs import CostConfig, CostMode, edge_cost
from .graph import Graph
from .shortest_path import dijkstra


# ---------------------------------------------------------------------------
# Min-cost max-flow
# ---------------------------------------------------------------------------
class _MCMF:
    def __init__(self, n: int):
        self.n = n
        self.to: list[int] = []
        self.cap: list[float] = []
        self.cost: list[float] = []
        self.head: list[list[int]] = [[] for _ in range(n)]

    def add(self, u: int, v: int, cap: float, cost: float) -> None:
        self.head[u].append(len(self.to)); self.to.append(v); self.cap.append(cap); self.cost.append(cost)
        self.head[v].append(len(self.to)); self.to.append(u); self.cap.append(0.0); self.cost.append(-cost)

    def flow(self, s: int, t: int):
        total_flow = 0.0
        total_cost = 0.0
        INF = math.inf
        while True:
            dist = [INF] * self.n
            in_q = [False] * self.n
            prev_e = [-1] * self.n
            dist[s] = 0.0
            q = deque([s]); in_q[s] = True
            while q:
                u = q.popleft(); in_q[u] = False
                for eid in self.head[u]:
                    if self.cap[eid] > 1e-12 and dist[u] + self.cost[eid] < dist[self.to[eid]] - 1e-12:
                        dist[self.to[eid]] = dist[u] + self.cost[eid]
                        prev_e[self.to[eid]] = eid
                        if not in_q[self.to[eid]]:
                            q.append(self.to[eid]); in_q[self.to[eid]] = True
            if dist[t] == INF:
                break
            # push max flow along found shortest path
            push = INF
            v = t
            while v != s:
                e = prev_e[v]
                push = min(push, self.cap[e])
                v = self.to[e ^ 1]
            v = t
            while v != s:
                e = prev_e[v]
                self.cap[e] -= push
                self.cap[e ^ 1] += push
                v = self.to[e ^ 1]
            total_flow += push
            total_cost += push * dist[t]
        return total_flow, total_cost


@dataclass
class Assignment:
    # evacuee source node -> {shelter node -> number assigned}
    flows: dict[int, dict[int, int]]
    total_cost: float
    served: int
    unserved: int


def min_cost_max_flow_assignment(
    graph: Graph,
    demands: dict[int, int],          # source node -> number of evacuees
    shelters: dict[int, int],         # shelter node -> capacity
    cfg: CostConfig | None = None,
) -> Assignment:
    """Assign evacuees to shelters minimising total shortest-path cost subject
    to shelter capacities. Uses pairwise shortest-path costs on a bipartite
    transportation graph (source -> shelter) wrapped in min-cost max-flow.
    """
    cfg = cfg or CostConfig(mode=CostMode.TIME)
    src_nodes = list(demands.keys())
    shelt_nodes = list(shelters.keys())
    # index: 0 = super-source, 1..S sources, S+1..S+H shelters, last = super-sink
    S, H = len(src_nodes), len(shelt_nodes)
    SS = 0
    src_idx = {n: 1 + i for i, n in enumerate(src_nodes)}
    sh_idx = {n: 1 + S + i for i, n in enumerate(shelt_nodes)}
    TT = 1 + S + H
    mc = _MCMF(TT + 1)

    for n in src_nodes:
        mc.add(SS, src_idx[n], float(demands[n]), 0.0)
    for n in shelt_nodes:
        mc.add(sh_idx[n], TT, float(shelters[n]), 0.0)

    # pairwise costs (shortest path source -> shelter); inf means unreachable
    SCALE = 1000.0  # integer-friendly cost scaling for stability
    for s in src_nodes:
        for h in shelt_nodes:
            res = dijkstra(graph, s, h, cfg)
            if res.found and not math.isinf(res.cost):
                mc.add(src_idx[s], sh_idx[h], float(demands[s]), res.cost)

    served, cost = mc.flow(SS, TT)

    # read back flows on source->shelter arcs
    flows: dict[int, dict[int, int]] = {s: {} for s in src_nodes}
    # reconstruct from residual capacities of forward arcs
    # forward arc indices were added in order; re-scan head lists
    for s in src_nodes:
        u = src_idx[s]
        for eid in mc.head[u]:
            v = mc.to[eid]
            if v in sh_idx.values() and eid % 2 == 0:  # forward arc
                used = mc.cap[eid ^ 1]  # flow equals reverse residual
                if used > 1e-9:
                    shelter_node = shelt_nodes[v - (1 + S)]
                    flows[s][shelter_node] = int(round(used))
    total_demand = sum(demands.values())
    return Assignment(flows=flows, total_cost=cost / SCALE if False else cost,
                      served=int(round(served)), unserved=total_demand - int(round(served)))


# ---------------------------------------------------------------------------
# BPR congestion + MSA
# ---------------------------------------------------------------------------
def bpr_time(t0: float, flow: float, capacity: float, a: float = 0.15, b: float = 4.0) -> float:
    """BPR volume-delay function. t0 free-flow time, flow veh/h, capacity veh/h."""
    c = max(capacity, 1e-6)
    return t0 * (1.0 + a * (flow / c) ** b)


@dataclass
class MSAResult:
    edge_flows: dict[int, float]          # edge id -> veh/h
    edge_times: dict[int, float]          # congested time
    iterations: int
    gap: float                            # relative gap at termination
    paths: dict[int, list[int]] = field(default_factory=dict)  # source -> edge ids


def msa_assignment(
    graph: Graph,
    demands: dict[int, int],
    shelters: dict[int, int],
    max_iter: int = 60,
    tol: float = 1e-3,
) -> MSAResult:
    """Congestion-aware assignment via Method of Successive Averages.

    Each iteration: assign all demand to current-shortest shelter at current
    congested times (all-or-nothing), then average with running flow using
    step size 1/k. Converges toward user equilibrium. Shelter capacity is
    enforced by routing to the min-cost feasible shelter via MCMF each
    iteration using current times.
    """
    edge_flows: dict[int, float] = {e: 0.0 for e in graph.edges}

    def congested_time(eid: int) -> float:
        e = graph.edges[eid]
        return bpr_time(e.free_flow_time_s, edge_flows[eid], e.capacity_veh_per_h)

    gap = math.inf
    k = 0
    for k in range(1, max_iter + 1):
        # set edge speeds to congested times by overriding free_flow_time_s copy
        snapshot = {eid: graph.edges[eid].free_flow_time_s for eid in graph.edges}
        for eid in graph.edges:
            graph.edges[eid].free_flow_time_s = congested_time(eid)
        try:
            assign = min_cost_max_flow_assignment(
                graph, demands, shelters, CostConfig(mode=CostMode.TIME))
            # all-or-nothing auxiliary flow for this iteration
            aux: dict[int, float] = {e: 0.0 for e in graph.edges}
            for s, dests in assign.flows.items():
                for h, cnt in dests.items():
                    res = dijkstra(graph, s, h, CostConfig(mode=CostMode.TIME))
                    for eid in res.edges:
                        aux[eid] += cnt
        finally:
            for eid, t in snapshot.items():
                graph.edges[eid].free_flow_time_s = t

        step = 1.0 / k
        new_flows = {eid: (1 - step) * edge_flows[eid] + step * aux[eid]
                     for eid in edge_flows}
        # relative gap
        num = sum(abs(new_flows[e] - edge_flows[e]) for e in edge_flows)
        den = sum(new_flows.values()) + 1e-9
        gap = num / den
        edge_flows = new_flows
        if gap < tol:
            break

    edge_times = {eid: congested_time(eid) for eid in graph.edges}
    return MSAResult(edge_flows=edge_flows, edge_times=edge_times,
                     iterations=k, gap=gap)
