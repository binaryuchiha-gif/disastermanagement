"""UNVERIFIED library-backed training path (Phase 2).

This mirrors risk_model/train.py but uses the full ML stack (LightGBM, XGBoost,
RandomForest, real SHAP, MLflow experiment tracking). It CANNOT run in the
sealed sandbox (no pip). Run it locally where you have internet:

    python -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    python -m risk_model.train_lib --config experiments/configs/model.yaml

It is deliberately import-guarded so merely importing this module in the sandbox
does not crash; calling main() without the deps raises a clear message.

Status: UNVERIFIED. The stdlib train.py produces REAL metrics on SYNTHETIC data;
this file produces the paper's REAL-DATA numbers once you run it on real inputs.
"""

from __future__ import annotations

import argparse

_REQUIRED = ["numpy", "pandas", "sklearn", "lightgbm", "shap", "mlflow"]


def _check_deps():
    missing = []
    for mod in _REQUIRED:
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    if missing:
        raise SystemExit(
            "UNVERIFIED path: missing packages " + ", ".join(missing) +
            ".\nInstall with: pip install -r requirements.txt\n"
            "Then: python -m risk_model.train_lib --config experiments/configs/model.yaml")


def main() -> None:  # pragma: no cover (requires libs not in sandbox)
    _check_deps()
    import mlflow
    import numpy as np
    import pandas as pd
    import shap
    from lightgbm import LGBMClassifier
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

    from pipeline.features import edge_features  # noqa: F401
    from risk_model.spatial_cv import train_test_split_spatial

    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--real", action="store_true",
                    help="use data/processed/real_dataset.parquet instead of synthetic")
    args = ap.parse_args()

    # Load dataset (REAL if available, else SYNTHETIC). Provenance must be tracked.
    if args.real:
        df = pd.read_parquet("data/processed/real_dataset.parquet")
        provenance = "REAL"
    else:
        from pipeline.synth_graph import generate
        from pipeline.synth_labeler import FEATURE_COLUMNS, build_dataset
        g = generate(seed=1234, nx=45, ny=45)
        df = pd.DataFrame(build_dataset(g, seed=0))
        provenance = "SYNTHETIC"

    feature_cols = [c for c in df.columns
                    if c not in ("label", "p_true", "scenario", "provenance",
                                 "edge_id", "cx", "cy", "twi_raw", "length_m",
                                 "min_elev_m", "slope_pct")]
    X = df[feature_cols].to_numpy()
    y = df["label"].to_numpy()
    rows = df.to_dict("records")

    mlflow.set_experiment("resqflow-x-risk")
    models = {
        "logistic": LogisticRegression(max_iter=1000),
        "random_forest": RandomForestClassifier(n_estimators=400, n_jobs=-1,
                                                 class_weight="balanced"),
        "lightgbm": LGBMClassifier(n_estimators=600, learning_rate=0.03,
                                   num_leaves=31, subsample=0.8),
    }

    for name, base in models.items():
        with mlflow.start_run(run_name=f"{provenance}_{name}"):
            aucs, praucs, briers = [], [], []
            for tr, te in train_test_split_spatial(rows, n_folds=5, seed=0):
                clf = CalibratedClassifierCV(base, method="isotonic", cv=3)
                clf.fit(X[tr], y[tr])
                p = clf.predict_proba(X[te])[:, 1]
                aucs.append(roc_auc_score(y[te], p))
                praucs.append(average_precision_score(y[te], p))
                briers.append(brier_score_loss(y[te], p))
            mlflow.log_param("provenance", provenance)
            mlflow.log_metric("roc_auc", float(np.mean(aucs)))
            mlflow.log_metric("pr_auc", float(np.mean(praucs)))
            mlflow.log_metric("brier", float(np.mean(briers)))
            print(f"[{provenance}] {name}: AUC={np.mean(aucs):.4f} "
                  f"PR-AUC={np.mean(praucs):.4f} Brier={np.mean(briers):.4f}")

    # SHAP on the LightGBM model (tree explainer)
    lgbm = LGBMClassifier(n_estimators=600, learning_rate=0.03).fit(X, y)
    explainer = shap.TreeExplainer(lgbm)
    shap_values = explainer.shap_values(X[:2000])
    shap.summary_plot(shap_values, df[feature_cols].iloc[:2000],
                      show=False)
    import matplotlib.pyplot as plt
    plt.savefig(f"results/shap_summary_{provenance}.png", bbox_inches="tight")
    print(f"[{provenance}] wrote results/shap_summary_{provenance}.png")


if __name__ == "__main__":
    main()
