"""ResQFlow-X data pipeline (Phase 1 + synthetic substitute).

- synth_graph: physics-informed SYNTHETIC city graph generator (sandbox-runnable).
- synth_labeler: physics-informed SYNTHETIC flood/road-failure labeler.
- features: edge/node feature engineering shared by real and synthetic paths.
- build_real_graph: REAL OSM+DEM pipeline (UNVERIFIED; needs internet + libs).
"""
