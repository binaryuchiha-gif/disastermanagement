"""Config-driven experiment runner (Phase 4).

Reproduces every SYNTHETIC table and figure with fixed seeds into results/.
Produces:
  * results/table_methods_SYNTHETIC.csv  -- per method x scenario aggregate
      metrics (mean +/- 95% CI over >=30 seeds) and paired tests vs baseline.
  * results/table_robustness_SYNTHETIC.csv -- model-misspecification stress test.
  * results/safety_time_SYNTHETIC.csv -- H3 safety-time curve.
  * results/manifest.json -- config hash, seeds, versions, file list.
  * figures via experiments.make_figures.

Every output is tagged SYNTHETIC. Deterministic given the config + seeds.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import random
import sys
import time

from pipeline.synth_graph import generate
from pipeline.synth_labeler import label_graph
from routing.chance_constrained import safety_time_curve
from sim import stats
from sim.simulator import SimConfig, simulate

RESULTS_DIR = "results"


def _load_config(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _prep_graph(cfg: dict, scenario: str, label_seed: int):
    """Build graph + true/model pfail fields for a scenario (both SYNTHETIC)."""
    gc = cfg["graph"]
    g = generate(seed=gc["seed"], nx=gc["nx"], ny=gc["ny"])
    lbl = label_graph(g, scenario, seed=label_seed, label_noise=cfg.get("label_noise", 0.05))
    true_pfail = {eid: info["p_true"] for eid, info in lbl.items()}
    return g, true_pfail


def _origins(g, n_origins: int, seed: int):
    rng = random.Random(seed)
    nonsh = [n.id for n in g.nodes.values() if not n.is_shelter]
    return rng.sample(nonsh, min(n_origins, len(nonsh)))


# metrics we collect per episode
_METRIC_KEYS = ["pct_reached", "pct_blocked_mid", "pct_failed",
                "mean_evac", "median_evac", "p95_evac", "reroutes", "overload"]


def _episode_metrics(res) -> dict:
    return {
        "pct_reached": res.pct_reached_safely(),
        "pct_blocked_mid": res.pct_blocked_midroute(),
        "pct_failed": res.pct_failed(),
        "mean_evac": res.mean_evac_time(),
        "median_evac": res.median_evac_time(),
        "p95_evac": res.p95_evac_time(),
        "reroutes": float(res.total_reroutes()),
        "overload": float(res.shelter_overload()),
    }


def run_methods_table(cfg: dict, smoke: bool) -> list[dict]:
    """H2/H4: compare methods across scenarios over many seeds, with CIs and
    paired Wilcoxon vs the baseline method."""
    rows = []
    base_method = cfg["baseline_method"]
    for scenario in cfg["scenarios"]:
        # collect per-method, per-seed metric samples
        samples: dict[str, dict[str, list[float]]] = {
            m: {k: [] for k in _METRIC_KEYS} for m in cfg["methods"]}
        for seed in cfg["seeds"]:
            g, true_pfail = _prep_graph(cfg, scenario, label_seed=seed)
            model_pfail = dict(true_pfail)  # perfect model for the main table
            origins = _origins(g, cfg["n_origins"], seed=seed + 999)
            for method in cfg["methods"]:
                sc = SimConfig(n_agents=cfg["n_agents"], seed=seed, method=method,
                               rerouting=True, congestion=True)
                res = simulate(g, origins, true_pfail, model_pfail, sc)
                m = _episode_metrics(res)
                for k in _METRIC_KEYS:
                    samples[method][k].append(m[k])

        for method in cfg["methods"]:
            row = {"SYNTHETIC": True, "scenario": scenario, "method": method,
                   "n_seeds": len(cfg["seeds"])}
            for k in _METRIC_KEYS:
                ci = stats.ci95(samples[method][k])
                row[f"{k}_mean"] = round(ci.mean, 3)
                row[f"{k}_ci_lo"] = round(ci.low, 3)
                row[f"{k}_ci_hi"] = round(ci.high, 3)
            # paired tests vs baseline on the key H2 metric (blocked_mid) and p95
            if method != base_method:
                for metric in ("pct_blocked_mid", "p95_evac"):
                    a = samples[method][metric]
                    b = samples[base_method][metric]
                    w = stats.wilcoxon_signed_rank(a, b)
                    d = stats.cliffs_delta(a, b)
                    row[f"{metric}_wilcoxon_p"] = round(w.p_value, 5)
                    row[f"{metric}_cliffs_delta"] = round(d, 3)
                    row[f"{metric}_effect"] = stats.cliffs_magnitude(d)
            rows.append(row)
    return rows


def run_robustness_table(cfg: dict) -> list[dict]:
    """Model-misspecification stress test: degrade the model_pfail by increasing
    noise and show how a risk-aware method degrades vs the shortest-path
    baseline (which ignores the model entirely)."""
    scenario = cfg.get("robustness_scenario", "extreme")
    method = cfg.get("robustness_method", "uncertainty")
    base = cfg["baseline_method"]
    rows = []
    for err in cfg["model_errors"]:
        samp_m = {k: [] for k in _METRIC_KEYS}
        samp_b = {k: [] for k in _METRIC_KEYS}
        for seed in cfg["seeds"]:
            g, true_pfail = _prep_graph(cfg, scenario, label_seed=seed)
            model_pfail = dict(true_pfail)
            origins = _origins(g, cfg["n_origins"], seed=seed + 999)
            r_m = simulate(g, origins, true_pfail, model_pfail,
                           SimConfig(n_agents=cfg["n_agents"], seed=seed,
                                     method=method, model_error=err))
            r_b = simulate(g, origins, true_pfail, model_pfail,
                           SimConfig(n_agents=cfg["n_agents"], seed=seed,
                                     method=base, model_error=err))
            for k in _METRIC_KEYS:
                samp_m[k].append(_episode_metrics(r_m)[k])
                samp_b[k].append(_episode_metrics(r_b)[k])
        row = {"SYNTHETIC": True, "scenario": scenario, "model_error": err}
        for k in ("pct_blocked_mid", "p95_evac", "pct_failed"):
            row[f"{method}_{k}"] = round(stats.ci95(samp_m[k]).mean, 3)
            row[f"{base}_{k}"] = round(stats.ci95(samp_b[k]).mean, 3)
        rows.append(row)
    return rows


def run_safety_time(cfg: dict) -> list[dict]:
    """H3: safety-time curve for a pair that actually HAS a safety/time tradeoff.

    A degenerate pair (every route blocks with prob 1) produces a flat,
    uninformative curve. We therefore select the (origin, shelter) pair with the
    largest gap between the fastest route's block probability and the safest
    achievable route's block probability -- i.e. the pair where trading time for
    safety matters most. This selection is itself seeded and reported.
    """
    g, true_pfail = _prep_graph(cfg, "extreme", label_seed=1)
    for eid, p in true_pfail.items():
        g.edges[eid].p_fail = p
    shelters = [n.id for n in g.nodes.values() if n.is_shelter]
    from routing.shortest_path import dijkstra, path_metrics
    from routing.costs import CostConfig, CostMode
    rng = random.Random(3)
    nonsh = [n.id for n in g.nodes.values() if not n.is_shelter]
    best = None  # (tradeoff_gap, source, target)
    for s in rng.sample(nonsh, min(80, len(nonsh))):
        for t in shelters:
            fast = dijkstra(g, s, t, CostConfig(mode=CostMode.TIME))
            safe = dijkstra(g, s, t, CostConfig(mode=CostMode.UNCERTAINTY))
            if not (fast.found and safe.found):
                continue
            fb = path_metrics(g, fast)["block_prob"]
            sb = path_metrics(g, safe)["block_prob"]
            gap = fb - sb
            # require the safe route to be meaningfully survivable
            if sb < 0.9 and (best is None or gap > best[0]):
                best = (gap, s, t)
    if best is None:
        # fallback: nearest shelter to a random origin
        s, t = rng.choice(nonsh), shelters[0]
    else:
        _, s, t = best
    alphas = [0.9, 0.7, 0.5, 0.3, 0.2, 0.1, 0.05, 0.02, 0.01]
    curve = safety_time_curve(g, s, t, alphas)
    for c in curve:
        c["SYNTHETIC"] = True
        c["source"] = s
        c["target"] = t
    return curve


def _write_csv(path: str, rows: list[dict]) -> None:
    if not rows:
        return
    keys = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--config", default="experiments/configs/default_SYNTHETIC.json")
    ap.add_argument("--smoke", action="store_true",
                    help="use the smoke config for a fast CI run")
    args = ap.parse_args()

    if args.smoke:
        args.config = "experiments/configs/smoke_SYNTHETIC.json"
    cfg = _load_config(args.config)
    os.makedirs(RESULTS_DIR, exist_ok=True)

    t0 = time.perf_counter()
    print(f"[SYNTHETIC] running experiments from {args.config} "
          f"({len(cfg['seeds'])} seeds x {len(cfg['scenarios'])} scenarios x "
          f"{len(cfg['methods'])} methods)")

    methods_rows = run_methods_table(cfg, args.smoke)
    _write_csv(f"{RESULTS_DIR}/table_methods_SYNTHETIC.csv", methods_rows)
    print(f"[SYNTHETIC] wrote table_methods_SYNTHETIC.csv ({len(methods_rows)} rows)")

    robo_rows = run_robustness_table(cfg)
    _write_csv(f"{RESULTS_DIR}/table_robustness_SYNTHETIC.csv", robo_rows)
    print(f"[SYNTHETIC] wrote table_robustness_SYNTHETIC.csv ({len(robo_rows)} rows)")

    st_rows = run_safety_time(cfg)
    _write_csv(f"{RESULTS_DIR}/safety_time_SYNTHETIC.csv", st_rows)
    print(f"[SYNTHETIC] wrote safety_time_SYNTHETIC.csv ({len(st_rows)} rows)")

    elapsed = time.perf_counter() - t0
    manifest = {
        "SYNTHETIC": True,
        "config_file": args.config,
        "config_sha256": hashlib.sha256(
            json.dumps(cfg, sort_keys=True).encode()).hexdigest()[:16],
        "seed": args.seed,
        "n_seeds": len(cfg["seeds"]),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "elapsed_s": round(elapsed, 2),
        "outputs": [
            "table_methods_SYNTHETIC.csv",
            "table_robustness_SYNTHETIC.csv",
            "safety_time_SYNTHETIC.csv",
        ],
        "note": "All results derived from SYNTHETIC data. NOT real-city findings.",
    }
    with open(f"{RESULTS_DIR}/manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"[SYNTHETIC] wrote manifest.json  (elapsed {elapsed:.1f}s)")

    # figures
    try:
        from experiments.make_figures import make_all
        make_all()
    except Exception as e:  # noqa: BLE001
        print(f"[WARN] figure generation skipped: {e}")


if __name__ == "__main__":
    main()
