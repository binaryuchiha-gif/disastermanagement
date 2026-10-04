"""Split-conformal prediction intervals for per-edge failure probability.

Given a calibration set, compute nonconformity scores (absolute residual between
calibrated probability and the 0/1 label) and take the (1-alpha) empirical
quantile q. For a new edge with predicted probability p, the conformal interval
is [p - q, p + q] clamped to [0,1]. The routing layer's UCB variant uses the
UPPER bound (risk-averse). This gives distribution-free marginal coverage under
exchangeability -- documented and tested for empirical coverage.

Reference: Vovk et al.; Angelopoulos & Bates, "A Gentle Introduction to
Conformal Prediction" (standard split-conformal construction).
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class SplitConformal:
    alpha: float = 0.1
    q: float = 0.0

    def fit(self, probs: list[float], y: list[int]) -> "SplitConformal":
        scores = sorted(abs(p - t) for p, t in zip(probs, y))
        n = len(scores)
        if n == 0:
            self.q = 0.0
            return self
        # conformal quantile index with finite-sample correction
        k = min(n - 1, math.ceil((n + 1) * (1 - self.alpha)) - 1)
        self.q = scores[k]
        return self

    def interval(self, p: float) -> tuple[float, float]:
        return (max(0.0, p - self.q), min(1.0, p + self.q))

    def intervals(self, probs: list[float]) -> list[tuple[float, float]]:
        return [self.interval(p) for p in probs]

    def coverage(self, probs: list[float], y: list[int]) -> float:
        """Empirical coverage: fraction of labels inside [lo, hi]. For a 0/1
        label the interval 'covers' if the label's distance to p is <= q."""
        if not probs:
            return float("nan")
        covered = sum(1 for p, t in zip(probs, y) if abs(p - t) <= self.q + 1e-12)
        return covered / len(probs)
