# ResQFlow-X Makefile
# The core targets (test, demo-graph, experiments) run with ONLY Python stdlib
# + pytest, i.e. they work in the sealed sandbox with no internet / no pip.

PYTHON ?= python
SEED   ?= 1234

.PHONY: help test test-v demo-graph experiments figures clean lint fmt \
        pipeline-real train-real tiles backend-run js-parity

help:
	@echo "ResQFlow-X targets:"
	@echo "  make test         - run stdlib test suite (routing, sim, model, stats)"
	@echo "  make demo-graph   - generate SYNTHETIC city graph + risk labels"
	@echo "  make experiments  - reproduce every SYNTHETIC table & figure -> results/"
	@echo "  make figures      - regenerate SVG figures from results/"
	@echo "  make clean        - remove generated artifacts"
	@echo "  --- require local internet + pip (UNVERIFIED in sandbox) ---"
	@echo "  make pipeline-real - build real graph from data/raw (OSM+DEM)"
	@echo "  make train-real    - train LightGBM/RF on real features"
	@echo "  make js-parity     - Python<->JS prediction parity test"
	@echo "  make tiles         - build offline PMTiles basemap"
	@echo "  make backend-run   - run FastAPI backend"

test:
	$(PYTHON) -m pytest

test-v:
	$(PYTHON) -m pytest -v

demo-graph:
	$(PYTHON) -m pipeline.synth_graph --seed $(SEED) --out data/processed/synthetic_city.json

experiments:
	$(PYTHON) -m experiments.run_all --seed $(SEED)

figures:
	$(PYTHON) -m experiments.make_figures

clean:
	rm -rf results/*.svg results/*.csv results/*.md results/manifest.json \
	       data/processed/*.json __pycache__ .pytest_cache
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +

lint:
	ruff check . || echo "ruff not installed (UNVERIFIED locally)"

fmt:
	ruff format . || echo "ruff not installed"

# --- UNVERIFIED (need internet + pip; see docs/REPRODUCE.md) ---
pipeline-real:
	$(PYTHON) -m pipeline.build_real_graph --config experiments/configs/chennai.yaml

train-real:
	$(PYTHON) -m risk_model.train --config experiments/configs/model.yaml

js-parity:
	$(PYTHON) -m risk_model.export_js --check-parity

tiles:
	bash scripts/build_tiles.sh
