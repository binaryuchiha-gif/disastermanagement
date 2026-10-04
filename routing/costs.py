"""Edge cost models shared by all routing algorithms.

The key research object is the *uncertainty-aware* cost. For an edge with
failure probability p, the probability it *survives* (stays passable) is
(1 - p). For a path, assuming independence across edges, the survival
probability is the product of per-edge survival probabilities. Maximising
survival probability is equivalent to MINIMISING the sum of
    -log(1 - p)
over edges (a nonnegative, additive cost). This turns a multiplicative
reliability objective into a standard additive shortest-path problem, so
Dijkstra/A* apply directly. This is the design that serves H2.

We expose several cost modes so the simulator and benchmarks can compare
baselines against the uncertainty-aware methods on identical graphs.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from .graph import Edge

_EPS = 1e-9
# cap on -log(1-p) so a single near-certain-failure edge is strongly avoided
# but never produces +inf (which would break tie-breaking / comparisons).
_SURV_CAP = 25.0  # corresponds to p_fail ~ 1 - e^-25


class CostMode(str, Enum):
    TIME = "time"                    # travel time only (Dijkstra baseline)
    DISTANCE = "distance"            # length only (shortest distance baseline)
    STATIC_RISK = "static_risk"      # time + lambda * static_risk (baseline 3)
    UNCERTAINTY = "uncertainty"      # time + beta * surv_penalty(p_fail)
    UNCERTAINTY_UCB = "uncertainty_ucb"  # risk-averse: uses conformal upper bound
    ACCESSIBILITY = "accessibility"  # profile-based (slopes/stairs/lit/low-lying)


def survival_penalty(p_fail: float) -> float:
    """-log(1 - p_fail), clamped. Nonnegative; 0 when p_fail == 0."""
    p = min(max(p_fail, 0.0), 1.0 - _EPS)
    return min(_SURV_CAP, -math.log(1.0 - p))


@dataclass
class AccessibilityProfile:
    """Profile-based penalties for Phase 3 item 9.

    Weights multiply normalized hazards. A wheelchair profile forbids stairs
    and heavily penalizes steep slopes; an elderly profile penalizes slopes and
    unlit/low-lying roads more than a default pedestrian.
    """

    name: str = "default"
    forbid_stairs: bool = False
    max_slope_pct: float = 100.0          # edges steeper than this are forbidden
    slope_weight: float = 0.0             # seconds penalty per percent grade per 100m
    unlit_penalty_s: float = 0.0          # flat penalty for unlit edges
    low_lying_weight: float = 0.0         # penalty scaled by (1 - min_elev norm)
    low_elev_ref_m: float = 0.0           # reference "safe" elevation

    @classmethod
    def wheelchair(cls) -> "AccessibilityProfile":
        return cls(
            name="wheelchair",
            forbid_stairs=True,
            max_slope_pct=8.0,
            slope_weight=4.0,
            unlit_penalty_s=0.0,
            low_lying_weight=0.0,
        )

    @classmethod
    def elderly(cls) -> "AccessibilityProfile":
        return cls(
            name="elderly",
            forbid_stairs=True,
            max_slope_pct=15.0,
            slope_weight=2.0,
            unlit_penalty_s=20.0,
            low_lying_weight=30.0,
            low_elev_ref_m=5.0,
        )

    @classmethod
    def pedestrian(cls) -> "AccessibilityProfile":
        return cls(name="pedestrian", forbid_stairs=False, max_slope_pct=100.0)


@dataclass
class CostConfig:
    mode: CostMode = CostMode.TIME
    lam_static: float = 300.0     # weight on static risk (seconds per unit risk)
    beta_surv: float = 300.0      # weight on survival penalty (seconds per nat)
    profile: AccessibilityProfile | None = None


def edge_cost(edge: Edge, cfg: CostConfig) -> float:
    """Return a nonnegative additive cost for traversing `edge` under `cfg`.

    Returns math.inf for forbidden edges (accessibility hard constraints).
    """
    t = edge.free_flow_time_s
    mode = cfg.mode

    if mode == CostMode.DISTANCE:
        return edge.length_m
    if mode == CostMode.TIME:
        return t
    if mode == CostMode.STATIC_RISK:
        return t + cfg.lam_static * edge.static_risk
    if mode == CostMode.UNCERTAINTY:
        return t + cfg.beta_surv * survival_penalty(edge.p_fail)
    if mode == CostMode.UNCERTAINTY_UCB:
        # risk-averse: use the conformal upper bound p_fail_hi if present
        p = edge.p_fail_hi if edge.p_fail_hi > 0 else edge.p_fail
        return t + cfg.beta_surv * survival_penalty(p)
    if mode == CostMode.ACCESSIBILITY:
        return _accessibility_cost(edge, cfg.profile or AccessibilityProfile.pedestrian())
    raise ValueError(f"unknown cost mode {mode}")


def _accessibility_cost(edge: Edge, prof: AccessibilityProfile) -> float:
    if prof.forbid_stairs and edge.has_stairs:
        return math.inf
    if abs(edge.slope_pct) > prof.max_slope_pct:
        return math.inf
    t = edge.free_flow_time_s
    t += prof.slope_weight * abs(edge.slope_pct) * (edge.length_m / 100.0)
    if not edge.lit:
        t += prof.unlit_penalty_s
    if prof.low_lying_weight > 0 and prof.low_elev_ref_m > 0:
        deficit = max(0.0, prof.low_elev_ref_m - edge.min_elev_m) / prof.low_elev_ref_m
        t += prof.low_lying_weight * deficit
    return t
