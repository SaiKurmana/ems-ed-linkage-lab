# EMS–ED Linkage Lab — synthetic data only.
PYTHON ?= python
CONFIG ?= config/default.yaml

.PHONY: all data simulate link analyze test lint site app clean install ci

all: data simulate link analyze

install:
	$(PYTHON) -m pip install -r requirements.txt

data:        ## generate synthetic population, EMS ePCRs, ED encounters, ground truth
	$(PYTHON) -m synth.generate --config $(CONFIG)

simulate:    ## run integration patterns A (HL7 v2 point-to-point), B (HIE), C (FHIR API)
	$(PYTHON) -m patterns.simulate --config $(CONFIG)

link:        ## deterministic UUID joins + Splink probabilistic linkage + evaluation
	$(PYTHON) -m linkage.run --config $(CONFIG)

analyze:     ## example analyses that linkage makes possible (demonstrations, not findings)
	$(PYTHON) -m analysis.run --config $(CONFIG)

test:
	$(PYTHON) -m pytest

lint:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .

site:        ## build static GitHub Pages site into _site/ from committed results
	$(PYTHON) -m site_src.build

app:
	$(PYTHON) -m streamlit run app/streamlit_app.py

ci:          ## small end-to-end run into a temp directory (used by GitHub Actions)
	$(PYTHON) -m pipeline_ci

clean:
	rm -rf data _site .pytest_cache .ruff_cache
