"""Tests for the Graph structure, geodesy, and serialization round-trip."""

from __future__ import annotations

import math

from pipeline.synth_graph import generate
from routing.graph import Edge, Graph, Node


def test_graph_build_and_adjacency():
    g = Graph()
    g.add_node(Node(0, 12.9, 80.2, elevation_m=5))
    g.add_node(Node(1, 12.91, 80.2, elevation_m=3))
    g.add_edge(Edge(0, 0, 1, length_m=100, speed_kph=36))
    assert g.n_nodes == 2 and g.n_edges == 1
    assert g.neighbors(0) == [1]
    assert g.in_edges(1)[0].u == 0
    # free-flow time computed: 100 m at 36 kph = 10 m/s -> 10 s
    assert abs(g.edges[0].free_flow_time_s - 10.0) < 1e-6


def test_haversine_known_distance():
    # ~1 degree of latitude ~ 111 km
    d = Graph.haversine_m(0.0, 0.0, 1.0, 0.0)
    assert 110_000 < d < 112_000


def test_serialization_roundtrip(tmp_path):
    g = generate(seed=7, nx=8, ny=8)
    p = tmp_path / "g.json"
    g.save_json(str(p))
    g2 = Graph.load_json(str(p))
    assert g2.n_nodes == g.n_nodes
    assert g2.n_edges == g.n_edges
    # edge attributes preserved
    e = next(iter(g.edges.values()))
    e2 = g2.edges[e.id]
    assert abs(e.length_m - e2.length_m) < 1e-9
    assert e.road_class == e2.road_class


def test_add_edge_unknown_node_raises():
    g = Graph()
    g.add_node(Node(0, 0, 0))
    try:
        g.add_edge(Edge(0, 0, 99, length_m=1))
        assert False, "expected KeyError"
    except KeyError:
        pass


def test_synth_graph_in_node_range():
    g = generate(seed=1234, nx=45, ny=45)  # 2025 nodes
    assert 2000 <= g.n_nodes <= 20000
    # shelters exist and have capacity
    sh = [n for n in g.nodes.values() if n.is_shelter]
    assert len(sh) >= 3
    assert all(n.shelter_capacity > 0 for n in sh)


def test_coordinates_are_finite_and_sane():
    g = generate(seed=5, nx=10, ny=10)
    for n in g.nodes.values():
        assert -90 <= n.lat <= 90
        assert -180 <= n.lon <= 180
        assert math.isfinite(n.elevation_m)
