"""Physics-informed SYNTHETIC road-failure labeler (Phase 2 ground-truth
substitute).

Produces, for each edge and a given rainfall scenario, a label
`flooded in {0,1}` and the latent true probability used to generate it. The
process encodes a simple rainfall-runoff + drainage-capacity threshold:

    hazard = w_rain*rain + w_twi*twi + w_elev*inv_elev + w_flow*flow_acc
             + w_water*near_water + w_hand*(1 - hand) + w_bridge*bridge
    p_true = sigmoid(k * (hazard - drainage_capacity))
    label  ~ Bernoulli(p_true)   with optional label noise

The point of exposing BOTH p_true and the sampled label is honesty: models are
trained on the noisy *labels*, and we can separately report how close learned
probabilities get to the generator's p_true (an oracle calibration check that is
only possible because the data is synthetic -- clearly flagged as such).

Rainfall scenarios: 'mild', 'moderate', 'extreme' map to normalised intensities.
All randomness is seeded. Pure stdlib.
"""

from __future__ import annotations

import math
import random

from routing.graph import Graph
from .features import edge_features

RAIN_SCENARIOS = {"mild": 0.25, "moderate": 0.55, "extreme": 0.9}

# Weights chosen so flood rates are realistic and spatially varied across
# scenarios (roughly: mild ~5-10%, moderate ~20-30%, extreme ~45-55%).
# Features are mean-centred (subtract ~0.5) so the hazard is signed, letting
# high-ground / well-drained edges stay dry even in extreme rain. Calibration
# was tuned empirically on the synthetic graph; see test_synth_labeler.
_W = {
    "rain": 3.2,
    "twi_norm": 1.1,
    "inv_elev_norm": 1.6,
    "flow_acc_norm": 1.1,
    "near_water_norm": 1.0,
    "hand": 1.2,          # low height-above-drainage -> more flooding
    "bridge_flag": 0.5,
}
_CENTER = 0.5             # feature centring constant
_RAIN_CENTER = 0.55      # rainfall centring (moderate scenario is the pivot)
_K = 4.0
_DRAINAGE_CAPACITY = 0.9  # threshold on the signed hazard; higher = better drained


def _sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    ez = math.exp(z)
    return ez / (1.0 + ez)


def label_graph(
    graph: Graph,
    scenario: str = "moderate",
    seed: int = 0,
    label_noise: float = 0.05,
    drainage_capacity: float = _DRAINAGE_CAPACITY,
) -> dict[int, dict]:
    """Return {edge_id: {p_true, label, scenario, rain}} for one scenario.

    `label_noise` randomly flips labels with this probability to emulate
    imperfect ground truth. p_true is the clean generator probability.
    """
    rng = random.Random((seed << 8) ^ hash(scenario) & 0xFFFFFFFF)
    rain = RAIN_SCENARIOS.get(scenario, 0.55)
    feats = edge_features(graph)
    out: dict[int, dict] = {}
    for eid, f in feats.items():
        hazard = (
            _W["rain"] * (rain - _RAIN_CENTER)
            + _W["twi_norm"] * (f["twi_norm"] - _CENTER)
            + _W["inv_elev_norm"] * (f["inv_elev_norm"] - _CENTER)
            + _W["flow_acc_norm"] * (f["flow_acc_norm"] - _CENTER)
            + _W["near_water_norm"] * (f["near_water_norm"] - _CENTER)
            + _W["hand"] * ((1.0 - f["hand_norm"]) - _CENTER)
            + _W["bridge_flag"] * f["bridge_flag"]
        )
        p_true = _sigmoid(_K * (hazard - drainage_capacity))
        label = 1 if rng.random() < p_true else 0
        if rng.random() < label_noise:
            label = 1 - label
        out[eid] = {"p_true": p_true, "label": label, "scenario": scenario, "rain": rain}
    return out


def build_dataset(
    graph: Graph,
    scenarios: list[str] | None = None,
    seed: int = 0,
    label_noise: float = 0.05,
) -> list[dict]:
    """Assemble a flat training dataset: one row per (edge, scenario).

    Each row = features + scenario variable (rain) + label + p_true + provenance
    tag 'SYNTHETIC'. Real and synthetic rows are never mixed: real rows (when
    they exist) carry provenance 'REAL' and come from a different builder.
    """
    scenarios = scenarios or ["mild", "moderate", "extreme"]
    feats = edge_features(graph)
    rows: list[dict] = []
    for sc in scenarios:
        labels = label_graph(graph, sc, seed=seed, label_noise=label_noise)
        rain = RAIN_SCENARIOS[sc]
        for eid, f in feats.items():
            row = dict(f)
            row["rain_norm"] = rain
            row["scenario"] = sc
            row["label"] = labels[eid]["label"]
            row["p_true"] = labels[eid]["p_true"]
            row["provenance"] = "SYNTHETIC"
            # add centroid for spatial CV blocking
            e = graph.edges[eid]
            nu, nv = graph.nodes[e.u], graph.nodes[e.v]
            row["cx"] = 0.5 * (nu.lon + nv.lon)
            row["cy"] = 0.5 * (nu.lat + nv.lat)
            rows.append(row)
    return rows


# feature columns used by the learned models (keep stable for parity export)
FEATURE_COLUMNS = [
    "inv_elev_norm", "inv_slope_norm", "twi_norm", "flow_acc_norm",
    "near_water_norm", "hand_norm", "bridge_flag", "road_primary", "rain_norm",
]
