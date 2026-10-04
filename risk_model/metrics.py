"""Classification + probability metrics (pure stdlib).

ROC-AUC, PR-AUC (average precision), F1 at a threshold, Brier score, log loss,
and calibration (reliability bins + Expected Calibration Error). Validated
against known values in the test suite.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


def _pairs(y_true, y_score):
    return sorted(zip(y_score, y_true), key=lambda t: t[0], reverse=True)


def roc_auc(y_true: list[int], y_score: list[float]) -> float:
    """AUC via the rank-sum (Mann-Whitney U) formula with tie handling."""
    pos = [s for s, y in zip(y_score, y_true) if y == 1]
    neg = [s for s, y in zip(y_score, y_true) if y == 0]
    n_pos, n_neg = len(pos), len(neg)
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    # rank all scores (average ranks for ties)
    alls = sorted(y_score)
    ranks = {}
    i = 0
    n = len(alls)
    while i < n:
        j = i
        while j + 1 < n and alls[j + 1] == alls[i]:
            j += 1
        avg = (i + 1 + j + 1) / 2.0
        ranks[alls[i]] = avg
        i = j + 1
    rank_sum_pos = sum(ranks[s] for s in pos)
    auc = (rank_sum_pos - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)
    return auc


def average_precision(y_true: list[int], y_score: list[float]) -> float:
    """PR-AUC as average precision (area under precision-recall, step)."""
    order = _pairs(y_true, y_score)
    n_pos = sum(y_true)
    if n_pos == 0:
        return float("nan")
    tp = 0
    fp = 0
    ap = 0.0
    prev_recall = 0.0
    for _, y in order:
        if y == 1:
            tp += 1
        else:
            fp += 1
        recall = tp / n_pos
        precision = tp / (tp + fp)
        ap += precision * (recall - prev_recall)
        prev_recall = recall
    return ap


def f1_at_threshold(y_true, y_score, thr: float) -> float:
    tp = sum(1 for y, s in zip(y_true, y_score) if s >= thr and y == 1)
    fp = sum(1 for y, s in zip(y_true, y_score) if s >= thr and y == 0)
    fn = sum(1 for y, s in zip(y_true, y_score) if s < thr and y == 1)
    if tp == 0:
        return 0.0
    prec = tp / (tp + fp)
    rec = tp / (tp + fn)
    return 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0


def best_f1_threshold(y_true, y_score) -> tuple[float, float]:
    cands = sorted(set(y_score))
    best = (0.0, 0.5)
    for thr in cands:
        f = f1_at_threshold(y_true, y_score, thr)
        if f > best[0]:
            best = (f, thr)
    return best  # (f1, threshold)


def brier_score(y_true, y_prob) -> float:
    return sum((p - y) ** 2 for y, p in zip(y_true, y_prob)) / len(y_true)


def log_loss(y_true, y_prob, eps: float = 1e-15) -> float:
    s = 0.0
    for y, p in zip(y_true, y_prob):
        p = min(max(p, eps), 1 - eps)
        s += -(y * math.log(p) + (1 - y) * math.log(1 - p))
    return s / len(y_true)


@dataclass
class Calibration:
    bins: list[dict]
    ece: float


def calibration(y_true, y_prob, n_bins: int = 10) -> Calibration:
    """Reliability bins + Expected Calibration Error."""
    bins = [{"lo": i / n_bins, "hi": (i + 1) / n_bins, "n": 0,
             "conf_sum": 0.0, "acc_sum": 0} for i in range(n_bins)]
    for y, p in zip(y_true, y_prob):
        idx = min(n_bins - 1, int(p * n_bins))
        bins[idx]["n"] += 1
        bins[idx]["conf_sum"] += p
        bins[idx]["acc_sum"] += y
    n = len(y_true)
    ece = 0.0
    out = []
    for b in bins:
        if b["n"] == 0:
            out.append({"lo": b["lo"], "hi": b["hi"], "n": 0,
                        "confidence": None, "accuracy": None})
            continue
        conf = b["conf_sum"] / b["n"]
        acc = b["acc_sum"] / b["n"]
        ece += (b["n"] / n) * abs(acc - conf)
        out.append({"lo": b["lo"], "hi": b["hi"], "n": b["n"],
                    "confidence": conf, "accuracy": acc})
    return Calibration(bins=out, ece=ece)


def summary(y_true, y_prob) -> dict:
    f1, thr = best_f1_threshold(y_true, y_prob)
    cal = calibration(y_true, y_prob)
    return {
        "roc_auc": roc_auc(y_true, y_prob),
        "pr_auc": average_precision(y_true, y_prob),
        "f1": f1,
        "f1_threshold": thr,
        "brier": brier_score(y_true, y_prob),
        "log_loss": log_loss(y_true, y_prob),
        "ece": cal.ece,
        "positive_rate": sum(y_true) / len(y_true),
        "n": len(y_true),
    }
