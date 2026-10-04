"""Tests for the evacuation simulator and the per-episode routing cache."""

from __future__ import annotations

import random

from pipeline.synth_graph import generate
from pipeline.synth_labeler import label_graph
from sim.routing_cache import ShelterTree
from sim.simulator import SimConfig, simulate
from routing.costs import CostMode


def _world(nx=18, scenario="extreme", label_seed=1):
    g = generate(seed=1234, nx=nx, ny=nx)
    lbl = label_graph(g, scenario, seed=label_seed)
    true_pfail = {eid: info["p_true"] for eid, info in lbl.items()}
    rng = random.Random(5)
    nonsh = [n.id for n in g.nodes.values() if not n.is_shelter]
    origins = rng.sample(nonsh, 40)
    return g, true_pfail, origins


def test_shelter_tree_reaches_shelters():
    g, true_pfail, _ = _world()
    for eid, p in true_pfail.items():
        g.edges[eid].p_fail = p
    tree = ShelterTree(g, CostMode.TIME)
    shelters = {n.id for n in g.nodes.values() if n.is_shelter}
    # most nodes should have a finite route to some shelter
    reachable = sum(1 for n in g.nodes if n in tree.dist and tree.dist[n] < float("inf"))
    assert reachable > 0.8 * g.n_nodes
    # route_from a sample node ends at a shelter
    sample = next(n for n in g.nodes if n not in shelters and n in tree.dist)
    sh, edges = tree.route_from(sample)
    assert sh in shelters
    if edges:
        assert g.edges[edges[-1]].v == sh or g.nodes[sh].is_shelter


def test_simulation_is_deterministic():
    g, true_pfail, origins = _world()
    cfg = SimConfig(n_agents=100, seed=42, method="uncertainty")
    r1 = simulate(g, origins, true_pfail, dict(true_pfail), cfg)
    r2 = simulate(g, origins, true_pfail, dict(true_pfail), cfg)
    o1 = [(o.agent_id, o.reached_shelter, round(o.evac_time_s, 4), o.failed) for o in r1.outcomes]
    o2 = [(o.agent_id, o.reached_shelter, round(o.evac_time_s, 4), o.failed) for o in r2.outcomes]
    assert o1 == o2


def test_shelter_capacity_never_exceeded():
    g, true_pfail, origins = _world()
    cfg = SimConfig(n_agents=400, seed=1, method="uncertainty")
    res = simulate(g, origins, true_pfail, dict(true_pfail), cfg)
    for s, used in res.shelter_utilization.items():
        assert used <= res.shelter_capacity[s], f"shelter {s} over capacity"


def test_metrics_in_valid_ranges():
    g, true_pfail, origins = _world()
    res = simulate(g, origins, true_pfail, dict(true_pfail),
                   SimConfig(n_agents=150, seed=3, method="static_risk"))
    assert 0.0 <= res.pct_reached_safely() <= 100.0
    assert 0.0 <= res.pct_blocked_midroute() <= 100.0
    assert res.total_reroutes() >= 0


def test_uncertainty_reduces_blockages_vs_shortest_with_perfect_model():
    """H2 (direction only): with a perfect model, uncertainty-aware routing
    should have <= blockages than shortest-distance, averaged over seeds."""
    g, true_pfail, origins = _world(nx=20)
    sd_block, un_block = [], []
    for seed in range(8):
        sd = simulate(g, origins, true_pfail, dict(true_pfail),
                      SimConfig(n_agents=200, seed=seed, method="shortest_distance"))
        un = simulate(g, origins, true_pfail, dict(true_pfail),
                      SimConfig(n_agents=200, seed=seed, method="uncertainty"))
        sd_block.append(sd.pct_blocked_midroute())
        un_block.append(un.pct_blocked_midroute())
    assert sum(un_block) / len(un_block) <= sum(sd_block) / len(sd_block) + 1e-9


def test_no_rerouting_increases_failures():
    """Disabling rerouting should not reduce failures (sanity of the mechanic)."""
    g, true_pfail, origins = _world(nx=18)
    with_rr = simulate(g, origins, true_pfail, dict(true_pfail),
                       SimConfig(n_agents=200, seed=2, method="uncertainty", rerouting=True))
    no_rr = simulate(g, origins, true_pfail, dict(true_pfail),
                     SimConfig(n_agents=200, seed=2, method="uncertainty", rerouting=False))
    assert no_rr.pct_failed() >= with_rr.pct_failed() - 1e-9
