"""Spatial block cross-validation (pure stdlib).

Random k-fold CV leaks information between spatially adjacent road edges (their
features and labels are correlated), inflating metrics. We instead partition the
study area into a grid of spatial blocks and assign whole blocks to folds, so no
edge in a test fold is adjacent to a training edge from the same block. This is
the standard remedy for spatial autocorrelation (Roberts et al. 2017).

Also provides a temporal-holdout helper: hold out one rainfall scenario entirely
(train on the others) to emulate temporal/event holdout where real event data
exists.
"""

from __future__ import annotations

import random


def spatial_block_folds(rows: list[dict], n_folds: int = 5, block_deg: float = 0.01,
                        seed: int = 0) -> list[list[int]]:
    """Return a list of folds; each fold is a list of ROW INDICES.

    Rows must carry 'cx','cy' (edge centroid lon/lat). Edges are grouped into
    square blocks of side `block_deg` degrees; whole blocks are assigned
    round-robin (shuffled) to folds.
    """
    rng = random.Random(seed)
    block_of = {}
    for i, r in enumerate(rows):
        bx = int(r["cx"] / block_deg)
        by = int(r["cy"] / block_deg)
        block_of.setdefault((bx, by), []).append(i)
    blocks = list(block_of.values())
    rng.shuffle(blocks)
    folds: list[list[int]] = [[] for _ in range(n_folds)]
    for bi, members in enumerate(blocks):
        folds[bi % n_folds].extend(members)
    return folds


def train_test_split_spatial(rows, n_folds=5, block_deg=0.01, seed=0):
    """Yield (train_idx, test_idx) for each spatial fold."""
    folds = spatial_block_folds(rows, n_folds, block_deg, seed)
    all_idx = set(range(len(rows)))
    for f in folds:
        test = set(f)
        train = list(all_idx - test)
        yield train, sorted(test)


def temporal_holdout(rows, holdout_scenario: str):
    """Return (train_idx, test_idx) holding out one scenario entirely."""
    train, test = [], []
    for i, r in enumerate(rows):
        (test if r.get("scenario") == holdout_scenario else train).append(i)
    return train, test
