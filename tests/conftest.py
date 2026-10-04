"""Shared pytest fixtures and a tiny stdlib 'property-based' helper.

The sandbox has no `hypothesis`, so we emulate property testing with a seeded
sampler `prop_cases(n, seed)` that yields deterministic random inputs. Tests
assert invariants hold across all generated cases. When `hypothesis` is
available locally, these can be upgraded to real `@given` strategies (see
docs/REPRODUCE.md), but the invariants tested are identical.
"""

from __future__ import annotations

import random

import pytest

from pipeline.synth_graph import generate
from pipeline.synth_labeler import label_graph


def prop_cases(n: int, seed: int = 0):
    """Yield n deterministic random.Random instances for property testing."""
    master = random.Random(seed)
    for _ in range(n):
        yield random.Random(master.random())


@pytest.fixture(scope="session")
def small_graph():
    """A deterministic small SYNTHETIC graph with risk applied (moderate rain)."""
    g = generate(seed=42, nx=12, ny=12)
    lbl = label_graph(g, "moderate", seed=3)
    for eid, info in lbl.items():
        g.edges[eid].p_fail = info["p_true"]
        g.edges[eid].static_risk = info["p_true"]
        g.edges[eid].p_fail_hi = min(1.0, info["p_true"] + 0.1)
        g.edges[eid].p_fail_lo = max(0.0, info["p_true"] - 0.1)
    return g


@pytest.fixture(scope="session")
def extreme_graph():
    g = generate(seed=1234, nx=20, ny=20)
    lbl = label_graph(g, "extreme", seed=1)
    for eid, info in lbl.items():
        g.edges[eid].p_fail = info["p_true"]
        g.edges[eid].static_risk = info["p_true"]
        g.edges[eid].p_fail_hi = min(1.0, info["p_true"] + 0.1)
    return g


@pytest.fixture(scope="session")
def shelters(small_graph):
    return [n.id for n in small_graph.nodes.values() if n.is_shelter]
