"""Tests for the crowd-report reliability scorer and adversarial evaluation."""

from __future__ import annotations

from backend.reliability import ReliabilityScorer, ReliabilityWeights, Report
from pipeline.synth_graph import generate
from pipeline.synth_labeler import label_graph
from sim.report_eval import simulate_reports


def test_score_in_unit_interval():
    scorer = ReliabilityScorer()
    r = Report(id="1", edge_id=0, lat=12.9, lon=80.2, reporter_id="a",
               timestamp=1000.0, reporter_lat=12.9, reporter_lon=80.2)
    s = scorer.score(r, [r], now=1000.0, model_pfail=0.7)
    assert 0.0 <= s["score"] <= 1.0


def test_agreement_increases_score():
    scorer = ReliabilityScorer()
    base = Report(id="1", edge_id=0, lat=12.9, lon=80.2, reporter_id="a",
                  timestamp=1000.0, reporter_lat=12.9, reporter_lon=80.2)
    corroboration = [
        Report(id=str(i), edge_id=0, lat=12.9001, lon=80.2001, reporter_id=f"r{i}",
               timestamp=1000.0) for i in range(2, 6)
    ]
    alone = scorer.score(base, [base], now=1000.0, model_pfail=0.5)["score"]
    together = scorer.score(base, [base] + corroboration, now=1000.0, model_pfail=0.5)["score"]
    assert together > alone


def test_recency_decay_lowers_old_reports():
    scorer = ReliabilityScorer(recency_halflife_s=3600.0)
    r = Report(id="1", edge_id=0, lat=12.9, lon=80.2, reporter_id="a", timestamp=0.0,
               reporter_lat=12.9, reporter_lon=80.2)
    fresh = scorer.score(r, [r], now=0.0, model_pfail=0.5)["components"]["recency"]
    old = scorer.score(r, [r], now=7200.0, model_pfail=0.5)["components"]["recency"]
    assert fresh > old
    assert abs(old - 0.25) < 1e-6  # two half-lives


def test_model_consistency_rewards_high_risk_edges():
    scorer = ReliabilityScorer()
    r = Report(id="1", edge_id=0, lat=12.9, lon=80.2, reporter_id="a", timestamp=0.0)
    high = scorer.score(r, [r], now=0.0, model_pfail=0.9)["score"]
    low = scorer.score(r, [r], now=0.0, model_pfail=0.05)["score"]
    assert high > low


def test_reporter_history_update():
    scorer = ReliabilityScorer()
    scorer.update_history("a", True)
    scorer.update_history("a", True)
    assert scorer.reporter_history["a"] > 0.5
    scorer.update_history("b", False)
    assert scorer.reporter_history["b"] < 0.5


def test_adversarial_robustness_precision_stays_high():
    """Precision (no false verified closures) must stay high even as adversarial
    reporters increase — the key safety property."""
    g = generate(seed=1234, nx=18, ny=18)
    lbl = label_graph(g, "extreme", seed=1)
    true_p = {eid: info["p_true"] for eid, info in lbl.items()}
    for frac in (0.0, 0.4, 0.6):
        res = simulate_reports(g, true_p, seed=3, adversarial_fraction=frac)
        # verified closures should essentially never be false positives
        assert res.precision >= 0.9, f"precision dropped at adv={frac}: {res.precision}"


def test_weights_normalize():
    w = ReliabilityWeights()
    parts = w.normalized()
    assert abs(sum(parts) - 1.0) < 1e-9
