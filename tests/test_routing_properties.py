"""Property-based correctness tests for the routing algorithms (Phase 3).

Key invariants (from the project spec):
  * All risk-aware methods reduce to Dijkstra (time) when risk = 0.
  * A* with an admissible heuristic returns the same optimal cost as Dijkstra.
  * Dijkstra cost equals the actual summed cost of the returned path.
  * Pareto front contains no dominated labels; it includes the min-time and
    min-risk extreme points.
  * Chance-constrained: achieved block prob is monotone non-increasing as alpha
    tightens (safer), and never worse than the fastest path.
  * D* Lite after a blockage equals full-recompute cost.
  * Min-cost max-flow respects capacities and conserves flow.
"""

from __future__ import annotations

import math

from pipeline.synth_graph import generate
from pipeline.synth_labeler import label_graph
from routing.assignment import min_cost_max_flow_assignment
from routing.chance_constrained import chance_constrained_route
from routing.costs import CostConfig, CostMode, edge_cost, survival_penalty
from routing.dynamic import DStarLite, full_recompute
from routing.pareto import pareto_routes
from routing.shortest_path import astar, dijkstra, path_metrics

from .conftest import prop_cases


def _apply_risk(g, scenario="moderate", seed=0):
    lbl = label_graph(g, scenario, seed=seed)
    for eid, info in lbl.items():
        g.edges[eid].p_fail = info["p_true"]
        g.edges[eid].static_risk = info["p_true"]
        g.edges[eid].p_fail_hi = min(1.0, info["p_true"] + 0.1)
    return g


# --- fundamental invariants -------------------------------------------------

def test_risk_aware_reduces_to_dijkstra_when_risk_zero():
    """With p_fail=0 and static_risk=0, uncertainty/static-risk == time."""
    g = generate(seed=11, nx=12, ny=12)
    for e in g.edges.values():
        e.p_fail = 0.0
        e.static_risk = 0.0
        e.p_fail_hi = 0.0
    shelters = [n.id for n in g.nodes.values() if n.is_shelter]
    base = dijkstra(g, 0, shelters[0], CostConfig(mode=CostMode.TIME))
    for mode in (CostMode.STATIC_RISK, CostMode.UNCERTAINTY, CostMode.UNCERTAINTY_UCB):
        r = dijkstra(g, 0, shelters[0], CostConfig(mode=mode))
        assert r.found == base.found
        assert abs(r.cost - base.cost) < 1e-6, f"{mode} diverged from Dijkstra"


def test_survival_penalty_zero_at_zero():
    assert survival_penalty(0.0) == 0.0
    assert survival_penalty(0.5) > 0
    # monotone increasing in p
    assert survival_penalty(0.9) > survival_penalty(0.5)


def test_dijkstra_cost_equals_path_sum():
    g = _apply_risk(generate(seed=3, nx=12, ny=12))
    shelters = [n.id for n in g.nodes.values() if n.is_shelter]
    for rng in prop_cases(20, seed=1):
        s = rng.randrange(g.n_nodes)
        t = rng.choice(shelters)
        cfg = CostConfig(mode=CostMode.UNCERTAINTY)
        r = dijkstra(g, s, t, cfg)
        if not r.found:
            continue
        summed = sum(edge_cost(g.edges[e], cfg) for e in r.edges)
        assert abs(summed - r.cost) < 1e-6


def test_astar_matches_dijkstra_cost():
    g = _apply_risk(generate(seed=9, nx=14, ny=14))
    shelters = [n.id for n in g.nodes.values() if n.is_shelter]
    checked = 0
    for rng in prop_cases(25, seed=2):
        s = rng.randrange(g.n_nodes)
        t = rng.choice(shelters)
        d = dijkstra(g, s, t, CostConfig(mode=CostMode.TIME))
        a = astar(g, s, t, CostConfig(mode=CostMode.TIME))
        assert d.found == a.found
        if d.found:
            assert abs(d.cost - a.cost) < 1e-6, f"A* != Dijkstra for {s}->{t}"
            checked += 1
    assert checked > 0


def test_astar_heuristic_admissible_never_overestimates():
    """A* cost must never be LESS than Dijkstra's optimum (admissibility =>
    optimality). If A* found a cheaper cost, the heuristic was inadmissible."""
    g = generate(seed=4, nx=14, ny=14)  # pure time, geometric
    shelters = [n.id for n in g.nodes.values() if n.is_shelter]
    for rng in prop_cases(25, seed=3):
        s = rng.randrange(g.n_nodes)
        t = rng.choice(shelters)
        d = dijkstra(g, s, t, CostConfig(mode=CostMode.TIME))
        a = astar(g, s, t, CostConfig(mode=CostMode.TIME))
        if d.found:
            assert a.cost >= d.cost - 1e-6


# --- Pareto -----------------------------------------------------------------

def test_pareto_front_has_no_dominated_labels():
    """Exact (non-eps) mode must return a front with no dominated labels."""
    g = _apply_risk(generate(seed=6, nx=10, ny=10), "extreme")
    shelters = [n.id for n in g.nodes.values() if n.is_shelter]
    for rng in prop_cases(8, seed=4):
        s = rng.randrange(g.n_nodes)
        t = rng.choice(shelters)
        front = pareto_routes(g, s, t, eps_dominance=False)
        vecs = [(p.time_s, p.risk, p.distance_m) for p in front]
        for i, a in enumerate(vecs):
            for j, b in enumerate(vecs):
                if i == j:
                    continue
                dominated = all(x <= y for x, y in zip(b, a)) and any(
                    x < y for x, y in zip(b, a))
                assert not dominated, f"label {a} dominated by {b}"


def test_pareto_eps_mode_is_bounded_and_nondominated():
    """Default eps-dominance mode must stay fast and return a non-dominated
    (within itself) front for a hard pair."""
    import time
    g = generate(seed=1234, nx=25, ny=25)
    lbl = label_graph(g, "extreme", seed=1)
    for eid, info in lbl.items():
        g.edges[eid].p_fail = info["p_true"]
    t0 = time.perf_counter()
    front = pareto_routes(g, 430, 6)  # eps-dominance default
    elapsed_ms = (time.perf_counter() - t0) * 1000
    assert front, "expected a non-empty front"
    assert elapsed_ms < 2000, f"eps pareto too slow: {elapsed_ms:.0f} ms"
    vecs = [(p.time_s, p.risk, p.distance_m) for p in front]
    for i, a in enumerate(vecs):
        for j, b in enumerate(vecs):
            if i != j:
                assert not (_dom(b, a)), f"{a} dominated by {b}"


def _dom(a, b):
    return all(x <= y for x, y in zip(a, b)) and any(x < y for x, y in zip(a, b))


def test_pareto_contains_time_optimal():
    """The min-time path from Dijkstra must appear (same time) in the front."""
    g = _apply_risk(generate(seed=8, nx=12, ny=12), "extreme")
    shelters = [n.id for n in g.nodes.values() if n.is_shelter]
    s, t = 0, shelters[0]
    dj = dijkstra(g, s, t, CostConfig(mode=CostMode.TIME))
    front = pareto_routes(g, s, t, eps_dominance=False)  # exact for this check
    assert dj.found and front
    min_time = min(p.time_s for p in front)
    assert abs(min_time - dj.cost) < 1e-6


# --- chance-constrained -----------------------------------------------------

def test_chance_constrained_monotone_in_alpha():
    g = _apply_risk(generate(seed=1234, nx=20, ny=20), "extreme")
    shelters = [n.id for n in g.nodes.values() if n.is_shelter]
    # choose a hard pair (long route) so there is a real tradeoff
    s, t = 430, 6
    alphas = [0.8, 0.5, 0.3, 0.1, 0.02]  # tightening
    prev_block = 1.1
    prev_time = -1.0
    for a in alphas:
        r = chance_constrained_route(g, s, t, a)
        if not r.path.found:
            continue
        # tighter alpha -> block prob should not increase (safer or equal)
        assert r.block_prob <= prev_block + 1e-6
        prev_block = r.block_prob
        # safer routes cost at least as much time (weakly)
        assert r.time_s >= prev_time - 1e-6 or r.block_prob < 1e-9
        prev_time = min(prev_time, r.time_s) if prev_time >= 0 else r.time_s


def test_chance_never_worse_than_fastest_block():
    g = _apply_risk(generate(seed=1234, nx=20, ny=20), "extreme")
    s, t = 430, 6
    fast = dijkstra(g, s, t, CostConfig(mode=CostMode.TIME))
    fast_block = path_metrics(g, fast)["block_prob"]
    cc = chance_constrained_route(g, s, t, alpha=0.1)
    assert cc.block_prob <= fast_block + 1e-6


# --- dynamic rerouting ------------------------------------------------------

def test_dstar_lite_matches_full_recompute_after_block():
    g = _apply_risk(generate(seed=5, nx=14, ny=14))
    shelters = [n.id for n in g.nodes.values() if n.is_shelter]
    cfg = CostConfig(mode=CostMode.TIME)
    checked = 0
    for rng in prop_cases(15, seed=5):
        s = rng.randrange(g.n_nodes)
        t = rng.choice(shelters)
        ds = DStarLite(g, s, t, cfg)
        p0 = ds.extract_path()
        if not p0.found or not p0.edges:
            continue
        blocked_edge = p0.edges[len(p0.edges) // 2]
        ds.update_edge_blocked(blocked_edge)
        pd = ds.extract_path()
        fr = full_recompute(g, s, t, cfg, {blocked_edge})
        assert pd.found == fr.found
        if pd.found:
            assert abs(pd.cost - fr.cost) < 1e-4, (
                f"D* Lite {pd.cost} != recompute {fr.cost} for {s}->{t}")
            checked += 1
    assert checked > 0


# --- assignment / flow ------------------------------------------------------

def test_mcmf_respects_capacity_and_conserves_flow():
    g = _apply_risk(generate(seed=2, nx=14, ny=14))
    shelters = [n.id for n in g.nodes.values() if n.is_shelter]
    caps = {sh: 30 for sh in shelters}
    demands = {0: 25, g.n_nodes - 1: 25, g.n_nodes // 2: 25}
    asg = min_cost_max_flow_assignment(g, demands, caps)
    # capacity never exceeded per shelter
    received = {sh: 0 for sh in shelters}
    for s, dests in asg.flows.items():
        for sh, cnt in dests.items():
            received[sh] += cnt
    for sh, cap in caps.items():
        assert received[sh] <= cap, f"shelter {sh} overloaded"
    # flow conservation: served + unserved == total demand
    assert asg.served + asg.unserved == sum(demands.values())
    # each source sends no more than its demand
    for s, dests in asg.flows.items():
        assert sum(dests.values()) <= demands[s]


def test_mcmf_serves_all_when_capacity_sufficient():
    g = _apply_risk(generate(seed=12, nx=12, ny=12))
    shelters = [n.id for n in g.nodes.values() if n.is_shelter]
    caps = {sh: 1000 for sh in shelters}
    demands = {0: 10, 5: 10}
    asg = min_cost_max_flow_assignment(g, demands, caps)
    assert asg.unserved == 0
