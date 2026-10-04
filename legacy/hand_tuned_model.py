"""Legacy baselines: a hand-tuned logistic road-failure model and a static-risk
rule. Pure Python standard library.

These are deliberately simple, explainable baselines (the kind the original
prototype used) so that H1 has something concrete to be measured against.
They are NOT trained; coefficients are hand-chosen to encode hydrological
intuition (low, flat, near-water road segments flood more).
"""

from __future__ import annotations

import math
from dataclasses import dataclass


def _sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    ez = math.exp(z)
    return ez / (1.0 + ez)


# Hand-tuned coefficients (explainable, not learned). Each feature is assumed
# to be provided on a roughly 0..1 normalized scale by the caller.
_W = {
    "bias": -1.4,
    "rain_norm": 2.2,          # more rain -> more failure
    "twi_norm": 1.6,           # higher topographic wetness index -> wetter
    "inv_elev_norm": 1.3,      # lower elevation -> more failure (inverted)
    "inv_slope_norm": 0.8,     # flatter -> water pools
    "near_water_norm": 1.1,    # closer to water/drain -> more failure
    "flow_acc_norm": 1.4,      # high flow accumulation -> more failure
    "bridge_flag": 0.5,        # bridges over water can be overtopped
}


@dataclass(frozen=True)
class LegacyPrediction:
    p_fail: float
    contributions: dict  # feature -> signed logit contribution (explainability)


def hand_tuned_risk(features: dict) -> float:
    """Return P(road segment impassable) in [0,1] from a hand-tuned logistic rule."""
    return hand_tuned_risk_explained(features).p_fail


def hand_tuned_risk_explained(features: dict) -> LegacyPrediction:
    z = _W["bias"]
    contrib = {"bias": _W["bias"]}
    for name, w in _W.items():
        if name == "bias":
            continue
        x = float(features.get(name, 0.0))
        c = w * x
        z += c
        contrib[name] = c
    return LegacyPrediction(p_fail=_sigmoid(z), contributions=contrib)


def static_risk(features: dict) -> float:
    """Static (non-probabilistic) risk score baseline in [0,1].

    A fixed weighted sum of hazard features, independent of rainfall scenario
    (this is the 'static risk' baseline referenced throughout the hypotheses).
    """
    score = (
        0.40 * float(features.get("inv_elev_norm", 0.0))
        + 0.25 * float(features.get("twi_norm", 0.0))
        + 0.20 * float(features.get("near_water_norm", 0.0))
        + 0.15 * float(features.get("flow_acc_norm", 0.0))
    )
    return max(0.0, min(1.0, score))
