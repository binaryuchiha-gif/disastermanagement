"""ResQFlow-X evacuation simulator (Phase 4).

A custom, seed-reproducible agent-based simulator (chosen over SUMO so it runs
with zero external dependencies in the sandbox; SUMO integration is a documented
stretch comparison). Agents evacuate from origins to shelters under stochastic
edge failures and congestion, using any routing method from Phase 3. The runner
sweeps scenarios/seeds and computes the statistics the hypotheses need.
"""
