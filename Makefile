PY := .venv/bin/python

setup:
	uv venv --python 3.12 .venv
	uv pip install --python $(PY) web3 requests pandas pydantic anthropic pyyaml
	$(PY) -m src.db

pull:
	$(PY) -m src.pull $(AGENT)

census:
	$(PY) -m src.census

golden-candidates:
	$(PY) -m src.golden_candidates

assess:
	$(PY) -m src.report $(AGENT)

judge-golden:
	$(PY) -m src.judge_golden

test: test-data

test-data:
	$(PY) -m src.test_data

test-census:
	$(PY) -m src.test_census

test-pipeline:
	$(PY) -m src.test_pipeline

.PHONY: setup pull census assess test test-data test-census test-pipeline
