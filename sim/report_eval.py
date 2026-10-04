"""Evaluate the crowd-report reliability scorer against adversarial/noisy
reporters (Phase 5 requirement). Pure stdlib — RUNS in the sandbox.

Setup: a set of edges are TRULY blocked. A population of reporters files reports;
some are honest (report true blockages near them), some are noisy (random), some
are adversarial (deliberately report false blockages to mislead routing). We run
the reliability scorer and measure how well score-thresholding recovers the true
blocked set (precision/recall/F1 of 'verified' vs truth) as the adversarial
fraction grows. This quantifies robustness to bad actors.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from backend.reliability import ReliabilityScorer, Report
from routing.graph import Graph


@dataclass
class ReportEvalResult:
    adversarial_fraction: float
    precision: float
    recall: float
    f1: float
    n_reports: int
    n_true_blocked: int
    n_verified: int


def simulate_reports(graph: Graph, true_pfail: dict[int, float], seed: int = 0,
                     n_reporters: int = 60, adversarial_fraction: float = 0.2,
                     noise_fraction: float = 0.2, threshold: float = 0.6,
                     now: float = 1_000_000.0) -> ReportEvalResult:
    rng = random.Random(seed)
    # ground truth: sample truly-blocked edges
    truly_blocked = {eid for eid, p in true_pfail.items() if rng.random() < p}
    edges = list(graph.edges.values())

    scorer = ReliabilityScorer()
    reports: list[Report] = []
    rid = 0

    n_adv = int(adversarial_fraction * n_reporters)
    n_noise = int(noise_fraction * n_reporters)
    n_honest = n_reporters - n_adv - n_noise

    def edge_point(e):
        u, v = graph.nodes[e.u], graph.nodes[e.v]
        return (0.5 * (u.lat + v.lat), 0.5 * (u.lon + v.lon))

    # honest reporters: report a true blockage near them (good history)
    blocked_list = list(truly_blocked)
    for _ in range(n_honest):
        reporter = f"honest_{rid}"
        scorer.reporter_history[reporter] = 0.85
        if blocked_list:
            e = graph.edges[rng.choice(blocked_list)]
            lat, lon = edge_point(e)
            reports.append(Report(id=f"r{rid}", edge_id=e.id, lat=lat, lon=lon,
                                  reporter_id=reporter, timestamp=now - rng.uniform(0, 600),
                                  reporter_lat=lat + rng.uniform(-0.0005, 0.0005),
                                  reporter_lon=lon + rng.uniform(-0.0005, 0.0005)))
        rid += 1

    # noisy reporters: random edges, neutral history
    for _ in range(n_noise):
        reporter = f"noisy_{rid}"
        scorer.reporter_history[reporter] = 0.5
        e = rng.choice(edges)
        lat, lon = edge_point(e)
        reports.append(Report(id=f"r{rid}", edge_id=e.id, lat=lat, lon=lon,
                              reporter_id=reporter, timestamp=now - rng.uniform(0, 3600),
                              reporter_lat=lat, reporter_lon=lon))
        rid += 1

    # adversarial reporters: report NON-blocked edges as blocked, poor history,
    # and far from the location (to look less credible)
    not_blocked = [e for e in edges if e.id not in truly_blocked]
    for _ in range(n_adv):
        reporter = f"adv_{rid}"
        scorer.reporter_history[reporter] = 0.2
        e = rng.choice(not_blocked) if not_blocked else rng.choice(edges)
        lat, lon = edge_point(e)
        reports.append(Report(id=f"r{rid}", edge_id=e.id, lat=lat, lon=lon,
                              reporter_id=reporter, timestamp=now - rng.uniform(0, 7200),
                              reporter_lat=lat + 0.01, reporter_lon=lon + 0.01))
        rid += 1

    model_pfail = {eid: p for eid, p in true_pfail.items()}
    verified = scorer.verified_edges(reports, now, model_pfail, threshold)

    tp = len(verified & truly_blocked)
    fp = len(verified - truly_blocked)
    fn = len(truly_blocked - verified)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return ReportEvalResult(adversarial_fraction, round(precision, 3), round(recall, 3),
                            round(f1, 3), len(reports), len(truly_blocked), len(verified))


def sweep_adversarial(graph, true_pfail, fractions, seed=0) -> list[ReportEvalResult]:
    return [simulate_reports(graph, true_pfail, seed=seed, adversarial_fraction=f)
            for f in fractions]
