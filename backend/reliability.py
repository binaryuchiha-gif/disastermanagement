"""Crowd-sourced hazard-report reliability scoring (Phase 5). Pure stdlib.

Each hazard report (e.g. "road X is blocked/flooded") gets a transparent
reliability score in [0,1] combining:

  * agreement    : how many independent reporters corroborate the same hazard
                   nearby (more independent agreement -> higher).
  * proximity    : reporter's distance to the reported location (closer -> higher).
  * model_consistency : agreement with the risk model's predicted p_fail for that
                   edge (a report of flooding on a high-risk edge is more
                   credible than on a low-risk edge).
  * reporter_history : the reporter's past accuracy (prior reports later verified).
  * recency      : exponential time decay (old reports matter less).

The final score is a transparent weighted combination (weights documented and
tunable). Reports above a threshold are treated as "verified blockages" and fed
to routing (edge p_fail -> 1). The scorer is evaluated in simulation against
adversarial/noisy reporters (sim/report_eval.py).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class Report:
    id: str
    edge_id: int
    lat: float
    lon: float
    reporter_id: str
    timestamp: float          # unix seconds
    hazard: str = "blocked"   # blocked|flooded|debris
    reporter_lat: float | None = None
    reporter_lon: float | None = None


@dataclass
class ReliabilityWeights:
    agreement: float = 0.30
    proximity: float = 0.15
    model_consistency: float = 0.25
    reporter_history: float = 0.20
    recency: float = 0.10

    def normalized(self):
        s = (self.agreement + self.proximity + self.model_consistency
             + self.reporter_history + self.recency)
        return (self.agreement / s, self.proximity / s, self.model_consistency / s,
                self.reporter_history / s, self.recency / s)


def _haversine_m(a_lat, a_lon, b_lat, b_lon):
    r = 6371008.8
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp = math.radians(b_lat - a_lat)
    dl = math.radians(b_lon - a_lon)
    x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(x)))


@dataclass
class ReliabilityScorer:
    weights: ReliabilityWeights = field(default_factory=ReliabilityWeights)
    agreement_radius_m: float = 150.0
    proximity_scale_m: float = 300.0
    recency_halflife_s: float = 3600.0  # 1 hour
    # reporter_id -> historical accuracy in [0,1] (prior verified fraction)
    reporter_history: dict = field(default_factory=dict)

    def score(self, report: Report, all_reports: list[Report], now: float,
              model_pfail: float | None = None) -> dict:
        wa, wp, wm, wh, wr = self.weights.normalized()

        # agreement: count independent reporters within radius reporting same edge/hazard
        reporters = set()
        for r in all_reports:
            if r.id == report.id:
                continue
            if r.hazard != report.hazard:
                continue
            d = _haversine_m(report.lat, report.lon, r.lat, r.lon)
            if d <= self.agreement_radius_m:
                reporters.add(r.reporter_id)
        reporters.discard(report.reporter_id)
        # saturating function: 0 agree ->0, 1->0.5, 2->0.67, 3->0.75 ...
        n_agree = len(reporters)
        agreement = n_agree / (n_agree + 1.0)

        # proximity: reporter distance to reported location
        if report.reporter_lat is not None:
            d = _haversine_m(report.lat, report.lon,
                             report.reporter_lat, report.reporter_lon)
            proximity = math.exp(-d / self.proximity_scale_m)
        else:
            proximity = 0.5  # unknown reporter location -> neutral

        # model consistency: how well the report agrees with model p_fail
        if model_pfail is not None:
            model_consistency = model_pfail  # high p_fail -> consistent with "blocked"
        else:
            model_consistency = 0.5

        # reporter history (prior accuracy); unknown reporter -> neutral 0.5
        history = self.reporter_history.get(report.reporter_id, 0.5)

        # recency decay
        age = max(0.0, now - report.timestamp)
        recency = 0.5 ** (age / self.recency_halflife_s)

        score = (wa * agreement + wp * proximity + wm * model_consistency
                 + wh * history + wr * recency)
        return {
            "report_id": report.id,
            "score": round(score, 4),
            "components": {
                "agreement": round(agreement, 4), "n_corroborating": n_agree,
                "proximity": round(proximity, 4),
                "model_consistency": round(model_consistency, 4),
                "reporter_history": round(history, 4),
                "recency": round(recency, 4),
            },
        }

    def verified_edges(self, reports: list[Report], now: float,
                       model_pfail: dict[int, float] | None = None,
                       threshold: float = 0.6) -> set[int]:
        """Return edge ids whose aggregated reports exceed the trust threshold."""
        model_pfail = model_pfail or {}
        verified = set()
        for r in reports:
            s = self.score(r, reports, now, model_pfail.get(r.edge_id))
            if s["score"] >= threshold:
                verified.add(r.edge_id)
        return verified

    def update_history(self, reporter_id: str, was_correct: bool, lr: float = 0.2):
        """Online update of a reporter's accuracy (EMA toward 1 if correct)."""
        prior = self.reporter_history.get(reporter_id, 0.5)
        target = 1.0 if was_correct else 0.0
        self.reporter_history[reporter_id] = (1 - lr) * prior + lr * target
