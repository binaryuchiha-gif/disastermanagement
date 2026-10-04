"""Permutation feature importance (pure stdlib) — a model-agnostic,
SHAP-adjacent attribution. For each feature, shuffle its column on the test set
and measure the increase in log loss; a larger increase => more important.
Deterministic given the seed. We sanity-check that top features match
hydrological intuition in docs/MODEL_CARD.md.

(Full Kernel/Tree SHAP needs the `shap` library and is provided in the
UNVERIFIED train_lib.py path.)
"""

from __future__ import annotations

import random

from .metrics import log_loss


def permutation_importance(model, X: list[list[float]], y: list[int],
                           feature_names: list[str], n_repeats: int = 5,
                           seed: int = 0) -> list[dict]:
    rng = random.Random(seed)
    base = log_loss(y, model.predict_proba(X))
    d = len(X[0])
    results = []
    for j in range(d):
        deltas = []
        for _ in range(n_repeats):
            Xp = [row[:] for row in X]
            col = [row[j] for row in Xp]
            rng.shuffle(col)
            for i in range(len(Xp)):
                Xp[i][j] = col[i]
            ll = log_loss(y, model.predict_proba(Xp))
            deltas.append(ll - base)
        mean_delta = sum(deltas) / len(deltas)
        results.append({"feature": feature_names[j], "importance": mean_delta})
    results.sort(key=lambda r: r["importance"], reverse=True)
    return results
