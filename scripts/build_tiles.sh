#!/usr/bin/env bash
# Build the offline PMTiles basemap for the study area. UNVERIFIED in sandbox
# (needs internet + Planetiler/tilemaker + a Geofabrik extract).
#
# Run locally:
#   bash scripts/build_tiles.sh
#
# Produces: pwa/public/tiles/study_area.pmtiles  (zoom 0-15, target tens of MB)
set -euo pipefail

AREA_PBF="${AREA_PBF:-data/raw/chennai.osm.pbf}"
OUT="${OUT:-pwa/public/tiles/study_area.pmtiles}"
BBOX="${BBOX:-80.18,12.93,80.25,13.02}"   # west,south,east,north

mkdir -p "$(dirname "$OUT")"

if [ ! -f "$AREA_PBF" ]; then
  echo "Downloading Geofabrik extract (southern-zone India) and clipping to bbox…"
  echo "  NOTE: respect OSM tile usage policy; do NOT bulk-scrape tile servers."
  echo "  1) Download: https://download.geofabrik.de/asia/india/southern-zone-latest.osm.pbf"
  echo "  2) Clip with osmium:  osmium extract -b $BBOX southern-zone-latest.osm.pbf -o $AREA_PBF"
  exit 1
fi

# Option A: Planetiler (recommended; Java)
if command -v java >/dev/null 2>&1 && [ -f planetiler.jar ]; then
  java -Xmx4g -jar planetiler.jar --osm-path="$AREA_PBF" --output="$OUT" \
    --minzoom=0 --maxzoom=15 --bounds="$BBOX" --force
# Option B: tilemaker
elif command -v tilemaker >/dev/null 2>&1; then
  tilemaker --input "$AREA_PBF" --output "$OUT" \
    --bbox "$BBOX" --config config.json --process process.lua
else
  echo "Neither Planetiler (planetiler.jar) nor tilemaker found."
  echo "Install one of them, then re-run. See docs/REPRODUCE.md."
  exit 1
fi

echo "Wrote $OUT"
ls -lh "$OUT"
echo "Remember to self-host fonts (glyph PBFs) under pwa/public/fonts/ and"
echo "sprites under pwa/public/sprites/ — missing glyphs cause blank labels."
