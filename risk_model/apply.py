"""Apply a trained risk model to a graph: set edge.p_fail (and conformal bounds)
from model predictions for a given rainfall scenario. Bridges Phase 2 (model)
and Phase 3/4 (routing/sim). Pure stdlib.
"""

from __future__ import annotations

from pipeline.features import edge_features
from pipeline.synth_labeler import RAIN_SCENARIOS
from routing.graph import Graph
from .conformal import SplitConformal
from .gbt import GradientBoostedTrees

_MODEL_FEATURES = [
    "inv_elev_norm", "inv_slope_norm", "twi_norm", "flow_acc_norm",
    "near_water_norm", "hand_norm", "bridge_flag", "road_primary", "rain_norm",
]


def apply_model_to_graph(graph: Graph, model: GradientBoostedTrees,
                         scenario: str = "moderate",
                         conformal: SplitConformal | None = None) -> None:
    """Set p_fail / p_fail_lo / p_fail_hi on every edge from the model."""
    rain = RAIN_SCENARIOS.get(scenario, 0.55)
    feats = edge_features(graph)
    for eid, f in feats.items():
        row = [
            f["inv_elev_norm"], f["inv_slope_norm"], f["twi_norm"],
            f["flow_acc_norm"], f["near_water_norm"], f["hand_norm"],
            f["bridge_flag"], f["road_primary"], rain,
        ]
        p = model.predict_proba([row])[0]
        e = graph.edges[eid]
        e.p_fail = p
        e.static_risk = p
        if conformal is not None:
            lo, hi = conformal.interval(p)
            e.p_fail_lo = lo
            e.p_fail_hi = hi
        else:
            e.p_fail_lo = p
            e.p_fail_hi = p
