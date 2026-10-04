"""Tests for accessibility profiles (Phase 3 item 9) and the routing facade,
including fail-safe behaviour required by Phase 6 / ETHICS."""

from __future__ import annotations

import math

from pipeline.synth_graph import generate
from pipeline.synth_labeler import label_graph
from routing.costs import AccessibilityProfile, CostConfig, CostMode, edge_cost
from routing.facade import route
from routing.graph import Edge, Graph, Node


def _risk_graph(seed=1, scenario="extreme"):
    g = generate(seed=seed, nx=14, ny=14)
    lbl = label_graph(g, scenario, seed=1)
    for eid, info in lbl.items():
        g.edges[eid].p_fail = info["p_true"]
        g.edges[eid].static_risk = info["p_true"]
    return g


def test_wheelchair_forbids_stairs():
    g = Graph()
    g.add_node(Node(0, 0, 0))
    g.add_node(Node(1, 0, 0.001))
    e = Edge(0, 0, 1, length_m=100, has_stairs=True)
    g.add_edge(e)
    cfg = CostConfig(mode=CostMode.ACCESSIBILITY, profile=AccessibilityProfile.wheelchair())
    assert math.isinf(edge_cost(e, cfg))
    # pedestrian allows stairs
    cfg2 = CostConfig(mode=CostMode.ACCESSIBILITY, profile=AccessibilityProfile.pedestrian())
    assert math.isfinite(edge_cost(e, cfg2))


def test_wheelchair_forbids_steep_slope():
    g = Graph()
    g.add_node(Node(0, 0, 0))
    g.add_node(Node(1, 0, 0.001))
    e = Edge(0, 0, 1, length_m=100, slope_pct=12.0)  # steeper than 8%
    g.add_edge(e)
    cfg = CostConfig(mode=CostMode.ACCESSIBILITY, profile=AccessibilityProfile.wheelchair())
    assert math.isinf(edge_cost(e, cfg))


def test_elderly_penalizes_but_allows_moderate_slope():
    g = Graph()
    g.add_node(Node(0, 0, 0))
    g.add_node(Node(1, 0, 0.001))
    e_flat = Edge(0, 0, 1, length_m=100, slope_pct=0.0, speed_kph=5)
    e_slope = Edge(1, 0, 1, length_m=100, slope_pct=10.0, speed_kph=5)
    g.add_edge(e_flat)
    g.add_edge(e_slope)
    prof = AccessibilityProfile.elderly()
    cfg = CostConfig(mode=CostMode.ACCESSIBILITY, profile=prof)
    c_flat = edge_cost(e_flat, cfg)
    c_slope = edge_cost(e_slope, cfg)
    assert math.isfinite(c_slope)
    assert c_slope > c_flat  # slope penalized


def test_facade_all_methods_return_route():
    g = _risk_graph()
    shelters = [n.id for n in g.nodes.values() if n.is_shelter]
    s, t = 0, shelters[0]
    for method in ("shortest_distance", "astar_time", "static_risk",
                   "uncertainty", "uncertainty_ucb", "chance_constrained",
                   "pareto_topsis", "accessibility"):
        resp = route(g, s, t, method=method)
        assert resp.path.found, f"{method} failed to find a route"
        assert "n_edges" in resp.explanation


def test_facade_failsafe_when_model_unavailable():
    g = _risk_graph()
    shelters = [n.id for n in g.nodes.values() if n.is_shelter]
    resp = route(g, 0, shelters[0], method="uncertainty", model_available=False)
    assert resp.fail_safe_triggered
    assert "fallback" in resp.method
    assert "unavailable" in resp.fail_safe_reason


def test_facade_failsafe_on_high_block_route():
    """For the known hard pair (fastest route ~0.98 block prob), uncertainty-aware
    routing must return a route no more dangerous than the fastest route, and the
    'why this route' explanation must be populated."""
    g = generate(seed=1234, nx=25, ny=25)
    lbl = label_graph(g, "extreme", seed=1)
    for eid, info in lbl.items():
        g.edges[eid].p_fail = info["p_true"]
        g.edges[eid].static_risk = info["p_true"]
    from routing.shortest_path import dijkstra, path_metrics
    from routing.costs import CostConfig, CostMode
    fast_block = path_metrics(
        g, dijkstra(g, 430, 6, CostConfig(mode=CostMode.TIME)))["block_prob"]
    resp = route(g, 430, 6, method="uncertainty",
                 low_confidence_block_threshold=0.8)
    # uncertainty-aware route is strictly safer than fastest here
    assert resp.metrics["block_prob"] <= fast_block + 1e-9
    assert resp.metrics["block_prob"] < 0.9  # measurably safer (fastest ~0.98)
    assert resp.explanation.get("riskiest_segments") is not None
