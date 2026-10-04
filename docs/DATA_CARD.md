# Data Card — ResQFlow-X

## Current data status
This repository was built in a **no-internet sandbox**, so all runnable results
use a **SYNTHETIC** city graph and a **physics-informed SYNTHETIC flood labeler**.
No real-city data has been ingested yet. Every synthetic artifact is tagged
`SYNTHETIC` in its filename, figures, tables, and docs.

| Dataset | Status | Provenance | License |
|---------|--------|-----------|---------|
| Road graph (synthetic) | ✅ in repo | `pipeline/synth_graph.py`, seed 1234 | project (MIT) |
| Flood labels (synthetic) | ✅ in repo | `pipeline/synth_labeler.py` (DEM-flow + rainfall thresholds + noise) | project (MIT) |
| Road graph (real, Chennai) | ⚠️ UNVERIFIED — you provide | OpenStreetMap via OSMnx | ODbL — **© OpenStreetMap contributors** |
| Elevation DEM (real) | ⚠️ UNVERIFIED — you provide | SRTMGL1 (NASA/USGS, ~30 m) | public domain |
| Rainfall (real) | ⚠️ UNVERIFIED — you provide | Open-Meteo historical and/or IMD gridded | per provider terms |
| Flood ground truth (real) | ⚠️ UNVERIFIED — you provide | Sentinel-1 SAR flood maps / govt/academic inundation maps / crowd reports | per provider terms |

## Study area (for the real pipeline)
Chennai — **Velachery + Adyar + Pallikaranai**, chosen for documented flooding
(2015 Chennai floods) and good OSM coverage. Bounding box in
`experiments/configs/chennai.yaml` (approx N 13.02 / S 12.93 / E 80.25 / W 80.18).
Target graph size 2,000–20,000 nodes.

## How the real data is obtained (reproducible, cached, scripted)
See `docs/REPRODUCE.md` for exact commands. Summary:
1. OSM drive network via OSMnx `graph_from_bbox` (cached under `data/raw/osmnx_cache`).
2. SRTM DEM GeoTIFF clipped to the bbox → node elevation, edge slope, min
   elevation, flow accumulation / TWI / height-above-nearest-drainage.
3. POIs (shelters, hospitals, high ground, fuel) via OSM tags; shelter capacity
   taken from OSM where tagged, else a **clearly-labeled assumption**
   (`default_shelter_capacity`, recorded here).
4. Rainfall from Open-Meteo/IMD for the configured events.

## Ground-truth labels (priority order, per the spec)
1. **Real flood evidence** — Sentinel-1 SAR flood extents / government/academic
   inundation maps / crowd reports for Chennai 2015 and later events.
2. **If unavailable** — the physics-informed SYNTHETIC labeler
   (`pipeline/synth_labeler.py`): DEM-based flow accumulation + rainfall-runoff
   + drainage-capacity thresholds with seeded label noise. **Stated as a
   limitation** in `docs/LIMITATIONS.md`; to be validated against any real flood
   evidence available.
> **Real and synthetic labels are never mixed silently.** Each row carries a
> `provenance` field (`REAL` / `SYNTHETIC`).

## Validation performed (runs in-sandbox on the synthetic graph)
From `pipeline/validate.py`: strongly-connected-component coverage, duplicate
edges, degenerate geometry, coordinate sanity, self-loops, and a landmark
snapping test (EPSG:4326 discipline). On the synthetic 45×45 graph: **100% SCC
coverage, 0 issues**, landmark snapping exact.

## Offline compression
Coordinate quantization (5 dp ≈ 1 m) + default-attribute dropping. Measured on
the synthetic 45×45 graph: **3112 KB → 700 KB (0.225×, ~4.4× smaller)**. The
real graph additionally ships as a `.pmtiles` basemap (see Phase 1B).

## Known gaps
- No real-city data ingested in this environment yet (sandbox has no internet).
- Synthetic shelter capacities and the synthetic flood process are modeling
  assumptions, not measurements.
- Conformal intervals are wide on the single-event synthetic labels.
