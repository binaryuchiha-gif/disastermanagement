"""Tests for the risk model: metrics correctness, model learning, calibration,
conformal coverage, and the H1 ordering on SYNTHETIC data."""

from __future__ import annotations

from pipeline.synth_graph import generate
from pipeline.synth_labeler import FEATURE_COLUMNS, build_dataset
from risk_model import metrics as M
from risk_model.calibration import IsotonicCalibrator, PlattScaler
from risk_model.conformal import SplitConformal
from risk_model.gbt import GradientBoostedTrees
from risk_model.logistic import LogisticRegression


# --- metrics validated against known values -------------------------------

def test_roc_auc_perfect_and_random():
    # perfectly separable
    y = [0, 0, 1, 1]
    s = [0.1, 0.2, 0.8, 0.9]
    assert abs(M.roc_auc(y, s) - 1.0) < 1e-9
    # reversed -> 0
    assert abs(M.roc_auc(y, [0.9, 0.8, 0.2, 0.1]) - 0.0) < 1e-9


def test_roc_auc_known_value():
    # classic small example: AUC = 0.75
    y = [1, 0, 1, 0]
    s = [0.9, 0.8, 0.4, 0.3]
    assert abs(M.roc_auc(y, s) - 0.75) < 1e-9


def test_brier_and_logloss_bounds():
    y = [1, 0, 1, 0]
    perfect = [1.0, 0.0, 1.0, 0.0]
    assert abs(M.brier_score(y, perfect)) < 1e-12
    assert M.log_loss(y, perfect) < 1e-6
    worst = [0.0, 1.0, 0.0, 1.0]
    assert M.brier_score(y, worst) > 0.9


def test_calibration_ece_perfect_is_zero():
    # if predicted prob equals empirical frequency in each bin, ECE ~ 0
    y = [1, 1, 0, 0, 1, 0, 1, 0, 1, 0]
    p = [0.5] * 10  # 50% positive, predicted 0.5
    cal = M.calibration(y, p, n_bins=10)
    assert cal.ece < 0.11  # single bin, |0.5-0.5|


# --- model learning --------------------------------------------------------

def _dataset(nx=16, seed=0):
    g = generate(seed=1234, nx=nx, ny=nx)
    rows = build_dataset(g, seed=seed)
    X = [[float(r[c]) for c in FEATURE_COLUMNS] for r in rows]
    y = [int(r["label"]) for r in rows]
    return X, y, rows


def test_logistic_learns_better_than_chance():
    X, y, _ = _dataset()
    lr = LogisticRegression(seed=0).fit(X, y, FEATURE_COLUMNS)
    auc = M.roc_auc(y, lr.predict_proba(X))
    assert auc > 0.7


def test_gbt_learns_and_beats_logistic_brier_insample():
    X, y, _ = _dataset()
    lr = LogisticRegression(seed=0).fit(X, y, FEATURE_COLUMNS)
    gbt = GradientBoostedTrees(n_estimators=40, seed=0).fit(X, y, FEATURE_COLUMNS)
    assert M.roc_auc(y, gbt.predict_proba(X)) > 0.75
    # GBT typically fits the flood pattern better in-sample
    assert M.brier_score(y, gbt.predict_proba(X)) <= M.brier_score(y, lr.predict_proba(X)) + 0.02


def test_gbt_probabilities_in_range():
    X, y, _ = _dataset()
    gbt = GradientBoostedTrees(n_estimators=20, seed=0).fit(X, y, FEATURE_COLUMNS)
    for p in gbt.predict_proba(X):
        assert 0.0 <= p <= 1.0


# --- calibration -----------------------------------------------------------

def test_platt_and_isotonic_monotone_and_bounded():
    scores = [i / 100 for i in range(100)]
    y = [1 if s > 0.5 else 0 for s in scores]
    platt = PlattScaler().fit(scores, y)
    out = platt.transform(scores)
    assert all(0 <= p <= 1 for p in out)
    # roughly increasing
    assert out[-1] > out[0]
    iso = IsotonicCalibrator().fit(scores, y)
    io = iso.transform(scores)
    assert all(0 <= p <= 1 for p in io)
    assert io[-1] >= io[0]


# --- conformal -------------------------------------------------------------

def test_conformal_coverage_meets_target():
    X, y, _ = _dataset(nx=18)
    n = len(X)
    i2 = int(0.7 * n)
    gbt = GradientBoostedTrees(n_estimators=30, seed=0).fit(X[:i2], y[:i2], FEATURE_COLUMNS)
    cal_p = gbt.predict_proba(X[i2:])
    conf = SplitConformal(alpha=0.1).fit(cal_p, y[i2:])
    cov = conf.coverage(cal_p, y[i2:])
    # split-conformal guarantees ~ (1-alpha) marginal coverage
    assert cov >= 0.88


def test_conformal_interval_within_unit():
    conf = SplitConformal(alpha=0.1)
    conf.q = 0.3
    lo, hi = conf.interval(0.9)
    assert 0.0 <= lo <= hi <= 1.0


# --- H1 ordering (the headline claim) --------------------------------------

def test_h1_learned_beats_handtuned_on_calibration():
    """On SYNTHETIC data, learned GBT must have far better calibration (ECE,
    Brier) than the hand-tuned legacy model."""
    from legacy.hand_tuned_model import hand_tuned_risk
    X, y, rows = _dataset(nx=18)
    gbt = GradientBoostedTrees(n_estimators=40, seed=0).fit(X, y, FEATURE_COLUMNS)
    gbt_p = gbt.predict_proba(X)
    hand_p = []
    for r in rows:
        feats = {"rain_norm": r["rain_norm"], "twi_norm": r["twi_norm"],
                 "inv_elev_norm": r["inv_elev_norm"], "inv_slope_norm": r["inv_slope_norm"],
                 "near_water_norm": r["near_water_norm"], "flow_acc_norm": r["flow_acc_norm"],
                 "bridge_flag": r["bridge_flag"]}
        hand_p.append(hand_tuned_risk(feats))
    assert M.brier_score(y, gbt_p) < M.brier_score(y, hand_p)
    assert M.calibration(y, gbt_p).ece < M.calibration(y, hand_p).ece
