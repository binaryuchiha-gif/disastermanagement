"""Training + evaluation orchestrator for the risk model (Phase 2).

Runs the full comparison for H1 on SYNTHETIC data (which this sandbox can run
end-to-end):
  baselines : hand-tuned legacy logistic, static risk, learned logistic
  candidate : gradient-boosted trees (headline learned model)
Evaluation: spatial block CV (no neighbour leakage) + a temporal (scenario)
holdout; metrics ROC-AUC, PR-AUC, F1, Brier, log-loss, ECE; isotonic/Platt
calibration measured by ECE improvement; split-conformal coverage; permutation
importance (checked against hydrological intuition); feature-group ablations.

Outputs:
  results/model_eval_SYNTHETIC.json  -- all metrics + CV folds + ablations
  data/processed/risk_model_SYNTHETIC.json -- the exported GBT (for JS parity)

The library-backed version (LightGBM/XGBoost/RandomForest + real SHAP + MLflow)
is in train_lib.py and is UNVERIFIED (needs pip). This stdlib version produces
REAL metrics on SYNTHETIC data.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics

from legacy.hand_tuned_model import hand_tuned_risk, static_risk
from pipeline.synth_graph import generate
from pipeline.synth_labeler import FEATURE_COLUMNS, build_dataset
from . import metrics as M
from .calibration import IsotonicCalibrator, PlattScaler
from .conformal import SplitConformal
from .gbt import GradientBoostedTrees
from .importance import permutation_importance
from .logistic import LogisticRegression
from .spatial_cv import temporal_holdout, train_test_split_spatial

RESULTS = "results"
PROC = "data/processed"


def _matrix(rows, cols=FEATURE_COLUMNS):
    X = [[float(r[c]) for c in cols] for r in rows]
    y = [int(r["label"]) for r in rows]
    return X, y


def _legacy_scores(rows, which="hand"):
    out = []
    for r in rows:
        feats = {
            "rain_norm": r["rain_norm"], "twi_norm": r["twi_norm"],
            "inv_elev_norm": r["inv_elev_norm"], "inv_slope_norm": r["inv_slope_norm"],
            "near_water_norm": r["near_water_norm"], "flow_acc_norm": r["flow_acc_norm"],
            "bridge_flag": r["bridge_flag"],
        }
        out.append(hand_tuned_risk(feats) if which == "hand" else static_risk(feats))
    return out


def spatial_cv_eval(rows, n_folds=5, seed=0) -> dict:
    """Spatial block CV for each model; returns per-model mean+/-std metrics."""
    models = ["legacy_hand_tuned", "static_risk", "logistic", "gbt"]
    agg = {m: {k: [] for k in ("roc_auc", "pr_auc", "f1", "brier", "log_loss", "ece")}
           for m in models}

    for train_idx, test_idx in train_test_split_spatial(rows, n_folds, seed=seed):
        tr = [rows[i] for i in train_idx]
        te = [rows[i] for i in test_idx]
        Xtr, ytr = _matrix(tr)
        Xte, yte = _matrix(te)

        preds = {}
        preds["legacy_hand_tuned"] = _legacy_scores(te, "hand")
        preds["static_risk"] = _legacy_scores(te, "static")
        lr = LogisticRegression(seed=seed).fit(Xtr, ytr, FEATURE_COLUMNS)
        preds["logistic"] = lr.predict_proba(Xte)
        gbt = GradientBoostedTrees(seed=seed).fit(Xtr, ytr, FEATURE_COLUMNS)
        preds["gbt"] = gbt.predict_proba(Xte)

        for m in models:
            s = M.summary(yte, preds[m])
            for k in agg[m]:
                v = s[k]
                if v == v:  # not NaN
                    agg[m][k].append(v)

    summary = {}
    for m in models:
        summary[m] = {k: {"mean": round(statistics.mean(v), 4),
                          "std": round(statistics.pstdev(v), 4) if len(v) > 1 else 0.0}
                      for k, v in agg[m].items() if v}
    return summary


def calibration_eval(rows, seed=0) -> dict:
    """Fit GBT on 60%, calibrate on 20%, test on 20% (spatial-ish random split
    by index since this is the SYNTHETIC single-event case). Report ECE before
    and after Platt and isotonic."""
    n = len(rows)
    i1, i2 = int(0.6 * n), int(0.8 * n)
    tr, cal, te = rows[:i1], rows[i1:i2], rows[i2:]
    Xtr, ytr = _matrix(tr)
    Xcal, ycal = _matrix(cal)
    Xte, yte = _matrix(te)
    gbt = GradientBoostedTrees(seed=seed).fit(Xtr, ytr, FEATURE_COLUMNS)
    raw_cal = gbt.predict_proba(Xcal)
    raw_te = gbt.predict_proba(Xte)

    platt = PlattScaler().fit(raw_cal, ycal)
    iso = IsotonicCalibrator().fit(raw_cal, ycal)

    ece_raw = M.calibration(yte, raw_te).ece
    ece_platt = M.calibration(yte, platt.transform(raw_te)).ece
    ece_iso = M.calibration(yte, iso.transform(raw_te)).ece

    # conformal coverage at alpha=0.1 (target >= 0.9)
    conf = SplitConformal(alpha=0.1).fit(iso.transform(raw_cal), ycal)
    cov = conf.coverage(iso.transform(raw_te), yte)

    return {
        "ece_uncalibrated": round(ece_raw, 4),
        "ece_platt": round(ece_platt, 4),
        "ece_isotonic": round(ece_iso, 4),
        "conformal_alpha": 0.1,
        "conformal_q": round(conf.q, 4),
        "conformal_empirical_coverage": round(cov, 4),
    }


def ablation_eval(rows, seed=0) -> list[dict]:
    """Feature-group ablations: remove one group at a time, measure ROC-AUC drop
    (GBT, temporal holdout on 'extreme')."""
    groups = {
        "terrain": ["inv_elev_norm", "inv_slope_norm", "twi_norm", "flow_acc_norm", "hand_norm"],
        "proximity": ["near_water_norm"],
        "scenario_rain": ["rain_norm"],
        "road_attrs": ["bridge_flag", "road_primary"],
    }
    tr_idx, te_idx = temporal_holdout(rows, "extreme")
    tr = [rows[i] for i in tr_idx]
    te = [rows[i] for i in te_idx]

    def auc_with(cols):
        Xtr = [[float(r[c]) for c in cols] for r in tr]
        ytr = [int(r["label"]) for r in tr]
        Xte = [[float(r[c]) for c in cols] for r in te]
        yte = [int(r["label"]) for r in te]
        if sum(yte) == 0 or sum(yte) == len(yte):
            return float("nan")
        gbt = GradientBoostedTrees(seed=seed).fit(Xtr, ytr, cols)
        return M.roc_auc(yte, gbt.predict_proba(Xte))

    full = auc_with(FEATURE_COLUMNS)
    out = [{"ablation": "full", "features": len(FEATURE_COLUMNS), "roc_auc": round(full, 4)}]
    for gname, gcols in groups.items():
        remaining = [c for c in FEATURE_COLUMNS if c not in gcols]
        if not remaining:
            continue
        auc = auc_with(remaining)
        out.append({"ablation": f"minus_{gname}", "features": len(remaining),
                    "roc_auc": round(auc, 4),
                    "auc_drop": round(full - auc, 4) if auc == auc else None})
    return out


def importance_eval(rows, seed=0) -> list[dict]:
    n = len(rows)
    tr, te = rows[:int(0.7 * n)], rows[int(0.7 * n):]
    Xtr, ytr = _matrix(tr)
    Xte, yte = _matrix(te)
    gbt = GradientBoostedTrees(seed=seed).fit(Xtr, ytr, FEATURE_COLUMNS)
    imp = permutation_importance(gbt, Xte, yte, FEATURE_COLUMNS, seed=seed)
    return [{"feature": r["feature"], "importance": round(r["importance"], 5)} for r in imp]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--nx", type=int, default=30)
    ap.add_argument("--config", default=None)  # accepted for Makefile parity
    args = ap.parse_args()

    os.makedirs(RESULTS, exist_ok=True)
    os.makedirs(PROC, exist_ok=True)

    g = generate(seed=1234, nx=args.nx, ny=args.nx)
    rows = build_dataset(g, seed=args.seed)
    print(f"[SYNTHETIC] dataset: {len(rows)} rows "
          f"({sum(r['label'] for r in rows)} positive), {len(FEATURE_COLUMNS)} features")

    cv = spatial_cv_eval(rows, seed=args.seed)
    cal = calibration_eval(rows, seed=args.seed)
    abl = ablation_eval(rows, seed=args.seed)
    imp = importance_eval(rows, seed=args.seed)

    # train final GBT on all data and export
    X, y = _matrix(rows)
    final = GradientBoostedTrees(seed=args.seed).fit(X, y, FEATURE_COLUMNS)
    with open(f"{PROC}/risk_model_SYNTHETIC.json", "w") as f:
        json.dump(final.to_dict(), f)

    report = {
        "SYNTHETIC": True,
        "provenance": "SYNTHETIC",
        "seed": args.seed,
        "n_rows": len(rows),
        "features": FEATURE_COLUMNS,
        "spatial_cv": cv,
        "calibration": cal,
        "ablations": abl,
        "permutation_importance": imp,
        "note": "H1 evidence on SYNTHETIC data. Rerun on REAL data via train_lib.py.",
    }
    with open(f"{RESULTS}/model_eval_SYNTHETIC.json", "w") as f:
        json.dump(report, f, indent=2)

    print("[SYNTHETIC] H1 spatial-CV ROC-AUC (mean):")
    for m, s in cv.items():
        print(f"    {m:18s} AUC={s.get('roc_auc',{}).get('mean','?')} "
              f"PR-AUC={s.get('pr_auc',{}).get('mean','?')} "
              f"Brier={s.get('brier',{}).get('mean','?')} "
              f"ECE={s.get('ece',{}).get('mean','?')}")
    print(f"[SYNTHETIC] calibration: {cal}")
    print(f"[SYNTHETIC] wrote model_eval_SYNTHETIC.json + risk_model_SYNTHETIC.json")


if __name__ == "__main__":
    main()
