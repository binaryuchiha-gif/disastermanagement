"""Tests for the Phase-1 pipeline: synthetic graph validity, compression,
CRS/snapping discipline, feature engineering, and the YAML subset loader."""

from __future__ import annotations

from pipeline.build_real_graph import _load_yaml
from pipeline.features import edge_features
from pipeline.synth_graph import generate
from pipeline.validate import (compact_graph, landmark_snap_test, size_report,
                               validate_graph)


def test_synthetic_graph_validates_clean():
    g = generate(seed=1234, nx=30, ny=30)
    rep = validate_graph(g)
    assert rep["passed"]
    assert rep["issues"]["bad_coords"] == 0
    assert rep["issues"]["zero_length"] == 0
    assert rep["scc_coverage_pct"] >= 60.0


def test_compression_reduces_size():
    g = generate(seed=1234, nx=30, ny=30)
    rep = size_report(g)
    assert rep["compact_bytes"] < rep["full_bytes"]
    assert rep["ratio"] < 0.6  # at least ~40% smaller


def test_compact_roundtrip_preserves_topology():
    g = generate(seed=7, nx=12, ny=12)
    comp = compact_graph(g)
    assert len(comp["nodes"]) == g.n_nodes
    assert len(comp["edges"]) == g.n_edges
    # ids preserved
    assert {n["id"] for n in comp["nodes"]} == set(g.nodes)


def test_landmark_snaps_to_correct_node():
    g = generate(seed=1234, nx=20, ny=20)
    target = g.nodes[42]
    lm = [{"name": "exact", "lat": target.lat, "lon": target.lon, "expect_within_m": 10}]
    res = landmark_snap_test(g, lm)
    assert res["all_ok"]
    assert res["landmarks"][0]["snapped_node"] == 42


def test_edge_features_present_and_normalized():
    g = generate(seed=3, nx=15, ny=15)
    feats = edge_features(g)
    assert len(feats) == g.n_edges
    sample = next(iter(feats.values()))
    for k in ("inv_elev_norm", "twi_norm", "flow_acc_norm", "near_water_norm", "hand_norm"):
        assert k in sample
        assert 0.0 <= sample[k] <= 1.0 + 1e-9


def test_yaml_subset_loader():
    import tempfile
    import os
    content = """
name: test
study_area:
  north: 13.02
  south: 12.93
flag: true
num: 5
ratio: 0.5
"""
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        f.write(content)
        p = f.name
    try:
        cfg = _load_yaml(p)
        assert cfg["name"] == "test"
        assert cfg["study_area"]["north"] == 13.02
        assert cfg["flag"] is True
        assert cfg["num"] == 5
        assert cfg["ratio"] == 0.5
    finally:
        os.unlink(p)
