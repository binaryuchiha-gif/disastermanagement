"""Validate the stdlib statistics against known textbook values."""

from __future__ import annotations

import math

from sim import stats


def test_mean_std():
    xs = [2, 4, 4, 4, 5, 5, 7, 9]
    assert abs(stats.mean(xs) - 5.0) < 1e-9
    # sample std (ddof=1) of this classic set is ~2.138; population std = 2.0
    assert abs(stats.std(xs, ddof=0) - 2.0) < 1e-9


def test_normal_cdf_known_values():
    assert abs(stats.normal_cdf(0.0) - 0.5) < 1e-6
    assert abs(stats.normal_cdf(1.96) - 0.975) < 2e-3
    assert abs(stats.normal_cdf(-1.96) - 0.025) < 2e-3


def test_ci95_contains_mean():
    xs = [10, 12, 9, 11, 13, 8, 10, 12, 11, 9]
    ci = stats.ci95(xs)
    assert ci.low < ci.mean < ci.high


def test_wilcoxon_known_direction():
    """b is uniformly larger than a -> significant, W small, p small."""
    a = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    b = [x + 5 for x in a]
    r = stats.wilcoxon_signed_rank(a, b)
    assert r.n == 10
    assert r.p_value < 0.05
    # all differences same sign -> W (min of rank sums) == 0
    assert r.statistic == 0.0


def test_wilcoxon_no_difference():
    a = [1, 2, 3, 4, 5]
    r = stats.wilcoxon_signed_rank(a, list(a))
    assert r.p_value == 1.0


def test_paired_t_direction():
    a = [10, 11, 9, 10, 12, 8, 11, 10, 9, 10]
    # b larger by a varying positive amount (non-constant difference)
    b = [x + d for x, d in zip(a, [2, 3, 1, 2, 4, 2, 3, 1, 2, 3])]
    r = stats.paired_t_test(a, b)
    assert r.p_value < 0.05
    assert r.statistic < 0  # a < b


def test_paired_t_constant_difference_is_degenerate():
    """A perfectly constant difference has zero variance -> handled, not crash."""
    a = [1, 2, 3, 4, 5]
    b = [x + 2 for x in a]
    r = stats.paired_t_test(a, b)
    assert r.note == "zero sd"
    assert r.p_value == 0.0  # mean diff != 0 with zero variance


def test_cliffs_delta_extremes():
    a = [1, 2, 3]
    b = [10, 11, 12]
    assert stats.cliffs_delta(a, b) == -1.0  # a entirely below b
    assert stats.cliffs_delta(b, a) == 1.0
    assert stats.cliffs_delta(a, list(a)) == 0.0


def test_cohens_d_sign():
    a = [1, 2, 3, 4, 5]
    # non-constant positive differences so std(diffs) > 0
    b = [x + d for x, d in zip(a, [1, 2, 1, 3, 2])]
    assert stats.cohens_d_paired(a, b) < 0  # a < b on average


def test_holm_bonferroni():
    # smallest p passes, correction tightens for the rest
    pvals = [0.001, 0.04, 0.03, 0.5]
    rej = stats.holm_bonferroni(pvals, alpha=0.05)
    assert rej[0] is True          # 0.001 <= 0.05/4
    assert rej[3] is False         # 0.5 never rejected


def test_cliffs_magnitude_bins():
    assert stats.cliffs_magnitude(0.1) == "negligible"
    assert stats.cliffs_magnitude(0.2) == "small"
    assert stats.cliffs_magnitude(0.4) == "medium"
    assert stats.cliffs_magnitude(0.8) == "large"
