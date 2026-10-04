"""Logistic regression via batch gradient descent (pure stdlib).

A learned baseline for H1 (vs the hand-tuned legacy model and vs the GBT). Keeps
coefficients interpretable (sign/magnitude per feature) which is useful for the
viva and for the SHAP-style sanity check against hydrological intuition.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field


def _sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    ez = math.exp(z)
    return ez / (1.0 + ez)


@dataclass
class LogisticRegression:
    lr: float = 0.1
    epochs: int = 300
    l2: float = 1e-3
    seed: int = 0
    weights: list[float] = field(default_factory=list)
    bias: float = 0.0
    feature_names: list[str] = field(default_factory=list)
    mean_: list[float] = field(default_factory=list)
    std_: list[float] = field(default_factory=list)

    def _standardize_fit(self, X):
        n = len(X)
        d = len(X[0])
        self.mean_ = [sum(row[j] for row in X) / n for j in range(d)]
        self.std_ = []
        for j in range(d):
            var = sum((row[j] - self.mean_[j]) ** 2 for row in X) / max(1, n - 1)
            self.std_.append(math.sqrt(var) or 1.0)

    def _standardize(self, row):
        return [(row[j] - self.mean_[j]) / self.std_[j] for j in range(len(row))]

    def fit(self, X: list[list[float]], y: list[int],
            feature_names: list[str] | None = None) -> "LogisticRegression":
        rng = random.Random(self.seed)
        n = len(X)
        d = len(X[0])
        self.feature_names = feature_names or [f"x{j}" for j in range(d)]
        self._standardize_fit(X)
        Xs = [self._standardize(row) for row in X]
        self.weights = [rng.uniform(-0.01, 0.01) for _ in range(d)]
        self.bias = 0.0
        for _ in range(self.epochs):
            grad_w = [0.0] * d
            grad_b = 0.0
            for i in range(n):
                z = self.bias + sum(self.weights[j] * Xs[i][j] for j in range(d))
                p = _sigmoid(z)
                err = p - y[i]
                for j in range(d):
                    grad_w[j] += err * Xs[i][j]
                grad_b += err
            for j in range(d):
                grad_w[j] = grad_w[j] / n + self.l2 * self.weights[j]
                self.weights[j] -= self.lr * grad_w[j]
            self.bias -= self.lr * (grad_b / n)
        return self

    def predict_proba(self, X: list[list[float]]) -> list[float]:
        out = []
        for row in X:
            rs = self._standardize(row)
            z = self.bias + sum(self.weights[j] * rs[j] for j in range(len(rs)))
            out.append(_sigmoid(z))
        return out

    def coef_report(self) -> dict:
        return {name: w for name, w in zip(self.feature_names, self.weights)}

    def to_dict(self) -> dict:
        return {"type": "logistic", "weights": self.weights, "bias": self.bias,
                "feature_names": self.feature_names, "mean": self.mean_, "std": self.std_}
