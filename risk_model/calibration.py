"""Probability calibration (pure stdlib): Platt scaling and isotonic regression.

Platt: fit a 1-D logistic on the model's raw scores -> probabilities.
Isotonic: pool-adjacent-violators (PAV) monotone fit of empirical accuracy vs
predicted probability. Both are fit on a held-out calibration split (never the
training or test fold) to avoid leakage.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


def _sigmoid(z):
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    ez = math.exp(z)
    return ez / (1.0 + ez)


@dataclass
class PlattScaler:
    a: float = 1.0
    b: float = 0.0

    def fit(self, scores: list[float], y: list[int], lr=0.1, epochs=500):
        # logits of probabilities as input is ideal, but raw prob works too
        n = len(scores)
        for _ in range(epochs):
            ga = gb = 0.0
            for s, t in zip(scores, y):
                p = _sigmoid(self.a * s + self.b)
                err = p - t
                ga += err * s
                gb += err
            self.a -= lr * ga / n
            self.b -= lr * gb / n
        return self

    def transform(self, scores):
        return [_sigmoid(self.a * s + self.b) for s in scores]


@dataclass
class IsotonicCalibrator:
    """Isotonic regression via Pool Adjacent Violators (PAV)."""
    x_thresholds: list[float] = field(default_factory=list)
    y_values: list[float] = field(default_factory=list)

    def fit(self, scores: list[float], y: list[int]):
        pairs = sorted(zip(scores, y))
        xs = [p[0] for p in pairs]
        ys = [float(p[1]) for p in pairs]
        w = [1.0] * len(ys)
        # PAV
        i = 0
        blocks = [[ys[k], w[k], xs[k]] for k in range(len(ys))]
        merged = []
        for b in blocks:
            merged.append(b[:])
            while len(merged) > 1 and merged[-2][0] > merged[-1][0]:
                last = merged.pop()
                prev = merged.pop()
                tw = prev[1] + last[1]
                val = (prev[0] * prev[1] + last[0] * last[1]) / tw
                merged.append([val, tw, prev[2]])
        # expand back to thresholds
        self.x_thresholds = []
        self.y_values = []
        # rebuild stepwise mapping
        xi = 0
        for blk in merged:
            self.x_thresholds.append(blk[2])
            self.y_values.append(min(1.0, max(0.0, blk[0])))
        return self

    def transform(self, scores):
        out = []
        for s in scores:
            # find last threshold <= s
            val = self.y_values[0] if self.y_values else 0.5
            for thr, v in zip(self.x_thresholds, self.y_values):
                if s >= thr:
                    val = v
                else:
                    break
            out.append(val)
        return out
