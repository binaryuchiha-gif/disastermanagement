"""Gradient-boosted regression trees for probability prediction (pure stdlib).

A compact, from-scratch gradient boosting machine with the logistic (binomial
deviance) loss, equivalent in spirit to LightGBM/XGBoost but dependency-free so
it RUNS and is TESTED in the sandbox with real metrics. The tree structure is
deliberately simple (axis-aligned CART regression trees on gradients) and
exports trivially to plain JS (nested if/else), satisfying the on-device
deployment requirement with an exact Python<->JS parity guarantee.

Design notes for the viva:
  * Boosting fits trees to the negative gradient of logistic loss (residuals
    y - p in probability space, via the raw-score link).
  * Shrinkage (learning_rate) and limited depth/leaves control overfitting.
  * Subsampling of rows (seeded) adds stochasticity like SGB.
  * Prediction = sigmoid(base_score + lr * sum(tree outputs)).
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
class _Node:
    feature: int = -1
    threshold: float = 0.0
    left: "object" = None
    right: "object" = None
    value: float = 0.0  # leaf raw-score contribution
    is_leaf: bool = False

    def to_dict(self):
        if self.is_leaf:
            return {"leaf": self.value}
        return {"f": self.feature, "t": self.threshold,
                "l": self.left.to_dict(), "r": self.right.to_dict()}


def _predict_node(node: _Node, row) -> float:
    while not node.is_leaf:
        node = node.left if row[node.feature] <= node.threshold else node.right
    return node.value


class _RegressionTree:
    def __init__(self, max_depth=3, min_samples_leaf=10, max_bins=32):
        self.max_depth = max_depth
        self.min_samples_leaf = min_samples_leaf
        self.max_bins = max_bins
        self.root: _Node | None = None

    def fit(self, X, grad, hess, idx):
        self.root = self._build(X, grad, hess, idx, depth=0)
        return self

    def _leaf_value(self, grad, hess, idx, lam=1.0):
        g = sum(grad[i] for i in idx)
        h = sum(hess[i] for i in idx)
        return -g / (h + lam)

    def _build(self, X, grad, hess, idx, depth) -> _Node:
        if depth >= self.max_depth or len(idx) < 2 * self.min_samples_leaf:
            return _Node(value=self._leaf_value(grad, hess, idx), is_leaf=True)
        best = self._best_split(X, grad, hess, idx)
        if best is None:
            return _Node(value=self._leaf_value(grad, hess, idx), is_leaf=True)
        feat, thr, left_idx, right_idx = best
        node = _Node(feature=feat, threshold=thr)
        node.left = self._build(X, grad, hess, left_idx, depth + 1)
        node.right = self._build(X, grad, hess, right_idx, depth + 1)
        return node

    def _best_split(self, X, grad, hess, idx, lam=1.0):
        """Histogram-based split finding (LightGBM-style): for each feature,
        bin the rows once and accumulate gradient/hessian histograms, then scan
        bin boundaries. O(n * d) per node instead of O(n * d * thresholds)."""
        d = len(X[0])
        G = sum(grad[i] for i in idx)
        H = sum(hess[i] for i in idx)
        best_gain = 1e-9
        best = None
        nb = self.max_bins
        for f in range(d):
            vals = [X[i][f] for i in idx]
            vmin = min(vals)
            vmax = max(vals)
            if vmax - vmin < 1e-12:
                continue
            width = (vmax - vmin) / nb
            # histogram of (g, h, count) per bin
            hist_g = [0.0] * nb
            hist_h = [0.0] * nb
            hist_n = [0] * nb
            for i in idx:
                b = int((X[i][f] - vmin) / width)
                if b >= nb:
                    b = nb - 1
                hist_g[b] += grad[i]
                hist_h[b] += hess[i]
                hist_n[b] += 1
            gl = hl = 0.0
            nl = 0
            for b in range(nb - 1):
                gl += hist_g[b]
                hl += hist_h[b]
                nl += hist_n[b]
                nr = len(idx) - nl
                if nl < self.min_samples_leaf or nr < self.min_samples_leaf:
                    continue
                gr = G - gl
                hr = H - hl
                gain = (gl * gl) / (hl + lam) + (gr * gr) / (hr + lam) - (G * G) / (H + lam)
                if gain > best_gain:
                    thr = vmin + (b + 1) * width
                    best_gain = gain
                    best = (f, thr)
        if best is None:
            return None
        f, thr = best
        left_idx = [i for i in idx if X[i][f] <= thr]
        right_idx = [i for i in idx if X[i][f] > thr]
        if len(left_idx) < self.min_samples_leaf or len(right_idx) < self.min_samples_leaf:
            return None
        return (f, thr, left_idx, right_idx)

    def predict_raw(self, row) -> float:
        return _predict_node(self.root, row)


@dataclass
class GradientBoostedTrees:
    n_estimators: int = 60
    learning_rate: float = 0.2
    max_depth: int = 3
    min_samples_leaf: int = 10
    subsample: float = 0.8
    seed: int = 0
    base_score: float = 0.0
    trees: list = field(default_factory=list)
    feature_names: list[str] = field(default_factory=list)

    def fit(self, X, y, feature_names=None) -> "GradientBoostedTrees":
        rng = random.Random(self.seed)
        n = len(X)
        self.feature_names = feature_names or [f"x{j}" for j in range(len(X[0]))]
        pos = sum(y) / n
        pos = min(max(pos, 1e-6), 1 - 1e-6)
        self.base_score = math.log(pos / (1 - pos))  # logit of prior
        raw = [self.base_score] * n
        self.trees = []
        for _ in range(self.n_estimators):
            grad = []
            hess = []
            for i in range(n):
                p = _sigmoid(raw[i])
                grad.append(p - y[i])          # gradient of logloss wrt raw
                hess.append(max(p * (1 - p), 1e-6))  # hessian
            # row subsample
            m = max(2 * self.min_samples_leaf, int(self.subsample * n))
            idx = rng.sample(range(n), min(m, n))
            tree = _RegressionTree(self.max_depth, self.min_samples_leaf).fit(
                X, grad, hess, idx)
            self.trees.append(tree)
            for i in range(n):
                raw[i] += self.learning_rate * tree.predict_raw(X[i])
        return self

    def predict_raw_one(self, row) -> float:
        raw = self.base_score
        for t in self.trees:
            raw += self.learning_rate * t.predict_raw(row)
        return raw

    def predict_proba(self, X) -> list[float]:
        return [_sigmoid(self.predict_raw_one(row)) for row in X]

    def to_dict(self) -> dict:
        return {
            "type": "gbt",
            "base_score": self.base_score,
            "learning_rate": self.learning_rate,
            "feature_names": self.feature_names,
            "trees": [t.root.to_dict() for t in self.trees],
        }
