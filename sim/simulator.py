"""Agent-based evacuation simulator (Phase 4).

Model (documented for the viva):
  * N agents each have an origin node, a departure time (sampled from a
    distribution), and a mode (vehicle/pedestrian).
  * The ground-truth world samples which edges ACTUALLY fail during the event
    from a probability field `true_pfail` (independent Bernoulli per edge). This
    is the reality the router does not see perfectly.
  * The router sees a (possibly wrong) `model_pfail` field and plans with a
    chosen Phase-3 cost mode. Robustness tests feed a deliberately perturbed
    model_pfail (model-misspecification stress test).
  * Routing uses a per-episode reverse multi-source shortest-path tree from all
    shelters (sim/routing_cache.py) so planning is O((V+E) log V) per episode,
    not per agent. Agents read their route off the tree in O(path length).
  * Agents advance along their planned route with an optional BPR congestion
    term. If an agent reaches an edge that has ACTUALLY failed, it is blocked:
    it reroutes (if enabled) around known-failed edges, else fails to evacuate.
  * Shelter capacity is enforced: when a shelter is full, late arrivals are
    turned away and reroute to the next-best shelter.

Everything is seeded.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from routing.costs import CostMode
from routing.graph import Graph
from .routing_cache import ShelterTree

# map high-level method name -> the cost mode used to build the shelter tree
_METHOD_COST = {
    "shortest_distance": CostMode.DISTANCE,
    "astar_time": CostMode.TIME,
    "shortest_time": CostMode.TIME,
    "static_risk": CostMode.STATIC_RISK,
    "uncertainty": CostMode.UNCERTAINTY,
    "uncertainty_ucb": CostMode.UNCERTAINTY_UCB,
    # chance_constrained is approximated in-sim by the uncertainty tree with a
    # high survival weight (documented); exact CC is used in the routing lib.
    "chance_constrained": CostMode.UNCERTAINTY_UCB,
}


@dataclass
class SimConfig:
    n_agents: int = 500
    seed: int = 0
    method: str = "uncertainty"
    alpha: float = 0.1
    rerouting: bool = True
    congestion: bool = True
    departure_window_s: float = 1800.0
    pedestrian_fraction: float = 0.2
    ped_speed_kph: float = 5.0
    model_error: float = 0.0
    max_sim_time_s: float = 36000.0


@dataclass
class AgentOutcome:
    agent_id: int
    origin: int
    reached_shelter: int | None
    evac_time_s: float
    blocked_midroute: bool
    n_reroutes: int
    failed: bool
    turned_away_full: bool = False


@dataclass
class SimResult:
    outcomes: list[AgentOutcome]
    config: SimConfig
    shelter_utilization: dict[int, int] = field(default_factory=dict)
    shelter_capacity: dict[int, int] = field(default_factory=dict)

    def evac_times(self) -> list[float]:
        return [o.evac_time_s for o in self.outcomes if not o.failed]

    def pct_reached_safely(self) -> float:
        if not self.outcomes:
            return 0.0
        return 100.0 * sum(1 for o in self.outcomes if not o.failed) / len(self.outcomes)

    def pct_blocked_midroute(self) -> float:
        if not self.outcomes:
            return 0.0
        return 100.0 * sum(1 for o in self.outcomes if o.blocked_midroute) / len(self.outcomes)

    def pct_failed(self) -> float:
        if not self.outcomes:
            return 0.0
        return 100.0 * sum(1 for o in self.outcomes if o.failed) / len(self.outcomes)

    def total_reroutes(self) -> int:
        return sum(o.n_reroutes for o in self.outcomes)

    def shelter_overload(self) -> int:
        return sum(1 for o in self.outcomes if o.turned_away_full)

    def mean_evac_time(self) -> float:
        t = self.evac_times()
        return sum(t) / len(t) if t else math.inf

    def p95_evac_time(self) -> float:
        t = sorted(self.evac_times())
        if not t:
            return math.inf
        idx = min(len(t) - 1, int(math.ceil(0.95 * len(t)) - 1))
        return t[idx]

    def median_evac_time(self) -> float:
        t = sorted(self.evac_times())
        if not t:
            return math.inf
        n = len(t)
        return t[n // 2] if n % 2 else 0.5 * (t[n // 2 - 1] + t[n // 2])

    def shelter_utilization_pct(self) -> dict[int, float]:
        return {s: 100.0 * self.shelter_utilization.get(s, 0) / c
                for s, c in self.shelter_capacity.items() if c > 0}

    def fairness_variance(self, origin_zone) -> float:
        zones: dict[int, list[float]] = {}
        for o in self.outcomes:
            if o.failed:
                continue
            zones.setdefault(origin_zone(o.origin), []).append(o.evac_time_s)
        means = [sum(v) / len(v) for v in zones.values() if v]
        if len(means) < 2:
            return 0.0
        mu = sum(means) / len(means)
        return sum((m - mu) ** 2 for m in means) / len(means)


def _bpr(t0: float, util: float) -> float:
    return t0 * (1.0 + 0.15 * util ** 4.0)


def simulate(
    graph: Graph,
    origins: list[int],
    true_pfail: dict[int, float],
    model_pfail: dict[int, float],
    cfg: SimConfig,
) -> SimResult:
    rng = random.Random(cfg.seed)

    # install model pfail (with optional robustness perturbation) onto edges
    for eid in graph.edges:
        p = model_pfail.get(eid, 0.0)
        if cfg.model_error > 0:
            p = min(1.0, max(0.0, p + rng.uniform(-cfg.model_error, cfg.model_error)))
        graph.edges[eid].p_fail = p
        graph.edges[eid].static_risk = p

    # sample TRUE failed edges for this episode
    failed_edges = {eid for eid, p in true_pfail.items() if rng.random() < p}

    cost_mode = _METHOD_COST.get(cfg.method, CostMode.UNCERTAINTY)
    tree = ShelterTree(graph, cost_mode)   # plan from all shelters once

    shelters = {n.id: n.shelter_capacity for n in graph.nodes.values()
                if n.is_shelter and n.shelter_capacity > 0}
    shelter_fill = {s: 0 for s in shelters}

    # edge congestion load counter (agents that have used each edge)
    edge_load: dict[int, int] = {eid: 0 for eid in graph.edges}

    # build agents
    agents = []
    for i in range(cfg.n_agents):
        origin = rng.choice(origins)
        dep = rng.uniform(0.0, cfg.departure_window_s)
        is_ped = rng.random() < cfg.pedestrian_fraction
        agents.append((i, origin, dep, is_ped))
    # process in departure order so congestion builds up realistically
    agents.sort(key=lambda a: a[2])

    outcomes = []
    for (aid, origin, dep, is_ped) in agents:
        outcomes.append(_run_agent(graph, aid, origin, dep, is_ped, cfg, tree,
                                   failed_edges, shelters, shelter_fill,
                                   edge_load, cost_mode, rng))

    return SimResult(outcomes, cfg, dict(shelter_fill), dict(shelters))


def _run_agent(graph, aid, origin, dep, is_ped, cfg, tree, failed_edges,
               shelters, shelter_fill, edge_load, cost_mode, rng) -> AgentOutcome:
    speed_factor = (cfg.ped_speed_kph / 30.0) if is_ped else 1.0
    full = {s for s, c in shelters.items() if shelter_fill[s] >= c}

    shelter, edges = tree.route_from(origin, avoid_shelters=full)
    if shelter is None or not edges and not graph.nodes[origin].is_shelter:
        # local recompute avoiding full shelters
        shelter, edges = _recompute(graph, origin, cost_mode, set(), full)
        if shelter is None:
            return AgentOutcome(aid, origin, None, math.inf, False, 0, True)

    t = dep
    n_reroutes = 0
    blocked_mid = False
    pos = origin
    idx = 0
    known_failed: set[int] = set()
    guard = 0

    while guard < 8 * graph.n_edges + 50:
        guard += 1
        if graph.nodes[pos].is_shelter and pos in shelters:
            if shelter_fill[pos] < shelters[pos]:
                shelter_fill[pos] += 1
                return AgentOutcome(aid, origin, pos, t - dep, blocked_mid, n_reroutes, False)
            full.add(pos)
            shelter, edges = _recompute(graph, pos, cost_mode, known_failed, full)
            if shelter is None:
                return AgentOutcome(aid, origin, None, math.inf, blocked_mid,
                                    n_reroutes, True, turned_away_full=True)
            n_reroutes += 1
            idx = 0
            continue

        if idx >= len(edges):
            # reached end of plan but not at shelter: recompute
            shelter, edges = _recompute(graph, pos, cost_mode, known_failed, full)
            if shelter is None:
                return AgentOutcome(aid, origin, None, math.inf, blocked_mid, n_reroutes, True)
            idx = 0
            continue

        eid = edges[idx]
        edge = graph.edges[eid]

        if eid in failed_edges:
            blocked_mid = True
            known_failed.add(eid)
            if not cfg.rerouting:
                return AgentOutcome(aid, origin, None, math.inf, True, n_reroutes, True)
            shelter, edges = _recompute(graph, pos, cost_mode, known_failed, full)
            if shelter is None:
                return AgentOutcome(aid, origin, None, math.inf, True, n_reroutes, True)
            n_reroutes += 1
            idx = 0
            continue

        tt = edge.free_flow_time_s / speed_factor
        if cfg.congestion:
            cap = max(1.0, edge.capacity_veh_per_h)
            util = edge_load[eid] / cap
            tt = _bpr(tt, min(util, 3.0))
        edge_load[eid] += 1
        t += tt
        if t - dep > cfg.max_sim_time_s:
            return AgentOutcome(aid, origin, None, math.inf, blocked_mid, n_reroutes, True)
        pos = edge.v
        idx += 1

    return AgentOutcome(aid, origin, None, math.inf, blocked_mid, n_reroutes, True)


def _recompute(graph, source, cost_mode, blocked, full):
    """Local recompute: a fresh shelter tree avoiding blocked edges, then read
    the route avoiding full shelters. Cheap relative to episode size and rare."""
    tree = ShelterTree(graph, cost_mode, blocked=set(blocked))
    return tree.route_from(source, avoid_shelters=full)
