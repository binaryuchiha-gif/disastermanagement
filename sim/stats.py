"""Statistics for the evaluation (Phase 4), pure Python standard library.

Since scipy is unavailable in the sandbox, we implement the needed tests from
their definitions and VALIDATE them against known textbook values in the test
suite. Implemented:

  * mean, std, 95% CI (t-approx and bootstrap)
  * paired Wilcoxon signed-rank test (normal approximation with continuity +
    tie correction) -> z and two-sided p
  * paired t-test
  * effect sizes: Cliff's delta (nonparametric) and Cohen's d (paired)
  * Holm-Bonferroni multiple-comparison correction

p-values use the normal approximation; for the sample sizes we use (>=30 seeds)
this is standard and adequate. The approximations and their validity range are
documented in docs/LIMITATIONS.md.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


def mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else float("nan")


def std(xs: list[float], ddof: int = 1) -> float:
    n = len(xs)
    if n <= ddof:
        return 0.0
    m = mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (n - ddof))


def _erf(x: float) -> float:
    # Abramowitz & Stegun 7.1.26 approximation
    sign = 1 if x >= 0 else -1
    x = abs(x)
    t = 1.0 / (1.0 + 0.3275911 * x)
    y = 1.0 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t
                - 0.284496736) * t + 0.254829592) * t * math.exp(-x * x)
    return sign * y


def normal_cdf(z: float) -> float:
    return 0.5 * (1.0 + _erf(z / math.sqrt(2.0)))


def two_sided_p_from_z(z: float) -> float:
    return 2.0 * (1.0 - normal_cdf(abs(z)))


@dataclass
class CI:
    mean: float
    low: float
    high: float
    std: float
    n: int


def ci95(xs: list[float]) -> CI:
    """95% CI using normal approx (z=1.96). For n>=30 this matches the t-dist
    closely; documented in LIMITATIONS."""
    n = len(xs)
    m = mean(xs)
    s = std(xs)
    half = 1.96 * s / math.sqrt(n) if n > 0 else float("nan")
    return CI(m, m - half, m + half, s, n)


def bootstrap_ci95(xs: list[float], n_boot: int = 2000, seed: int = 0) -> CI:
    import random
    rng = random.Random(seed)
    n = len(xs)
    if n == 0:
        return CI(float("nan"), float("nan"), float("nan"), 0.0, 0)
    boots = []
    for _ in range(n_boot):
        sample = [xs[rng.randrange(n)] for _ in range(n)]
        boots.append(mean(sample))
    boots.sort()
    lo = boots[int(0.025 * n_boot)]
    hi = boots[int(0.975 * n_boot)]
    return CI(mean(xs), lo, hi, std(xs), n)


@dataclass
class TestResult:
    statistic: float
    z: float
    p_value: float
    n: int
    note: str = ""


def wilcoxon_signed_rank(a: list[float], b: list[float]) -> TestResult:
    """Paired Wilcoxon signed-rank test (two-sided, normal approximation with
    tie and continuity correction). Returns W (sum of positive ranks), z, p."""
    if len(a) != len(b):
        raise ValueError("paired samples must have equal length")
    diffs = [x - y for x, y in zip(a, b) if x - y != 0.0]
    n = len(diffs)
    if n == 0:
        return TestResult(0.0, 0.0, 1.0, 0, "all pairs tied")
    absd = sorted((abs(d), i) for i, d in enumerate(diffs))
    # assign ranks with ties averaged
    ranks = [0.0] * n
    i = 0
    tie_term = 0.0
    while i < n:
        j = i
        while j + 1 < n and absd[j + 1][0] == absd[i][0]:
            j += 1
        avg_rank = (i + 1 + j + 1) / 2.0
        t = j - i + 1
        if t > 1:
            tie_term += t ** 3 - t
        for k in range(i, j + 1):
            ranks[absd[k][1]] = avg_rank
        i = j + 1
    w_plus = sum(r for d, r in zip(diffs, ranks) if d > 0)
    w_minus = sum(r for d, r in zip(diffs, ranks) if d < 0)
    w = min(w_plus, w_minus)
    mean_w = n * (n + 1) / 4.0
    var_w = (n * (n + 1) * (2 * n + 1) - tie_term / 2.0) / 24.0
    if var_w <= 0:
        return TestResult(w, 0.0, 1.0, n, "zero variance")
    # continuity correction
    z = (w - mean_w + 0.5) / math.sqrt(var_w) if w < mean_w else (w - mean_w - 0.5) / math.sqrt(var_w)
    return TestResult(statistic=w, z=z, p_value=two_sided_p_from_z(z), n=n)


def paired_t_test(a: list[float], b: list[float]) -> TestResult:
    diffs = [x - y for x, y in zip(a, b)]
    n = len(diffs)
    if n < 2:
        return TestResult(0.0, 0.0, 1.0, n, "n<2")
    m = mean(diffs)
    s = std(diffs)
    if s == 0:
        return TestResult(float("inf") if m != 0 else 0.0, 0.0,
                          0.0 if m != 0 else 1.0, n, "zero sd")
    t = m / (s / math.sqrt(n))
    # treat t as z (normal approx) for p; adequate for n>=30
    return TestResult(statistic=t, z=t, p_value=two_sided_p_from_z(t), n=n)


def cliffs_delta(a: list[float], b: list[float]) -> float:
    """Nonparametric effect size in [-1, 1]. delta>0 means a tends larger."""
    gt = lt = 0
    for x in a:
        for y in b:
            if x > y:
                gt += 1
            elif x < y:
                lt += 1
    n = len(a) * len(b)
    return (gt - lt) / n if n else 0.0


def cohens_d_paired(a: list[float], b: list[float]) -> float:
    diffs = [x - y for x, y in zip(a, b)]
    s = std(diffs)
    return mean(diffs) / s if s else 0.0


def holm_bonferroni(pvals: list[float], alpha: float = 0.05) -> list[bool]:
    """Return list of reject/accept decisions after Holm-Bonferroni correction."""
    m = len(pvals)
    order = sorted(range(m), key=lambda i: pvals[i])
    reject = [False] * m
    for rank, idx in enumerate(order):
        thresh = alpha / (m - rank)
        if pvals[idx] <= thresh:
            reject[idx] = True
        else:
            break
    return reject


def cliffs_magnitude(delta: float) -> str:
    d = abs(delta)
    if d < 0.147:
        return "negligible"
    if d < 0.33:
        return "small"
    if d < 0.474:
        return "medium"
    return "large"
