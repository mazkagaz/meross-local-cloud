PYTHON ?= python3

.PHONY: install test test-fast test-functional test-contracts compile reports

install:
	$(PYTHON) -m pip install -r tests/requirements_test.txt

test:
	$(PYTHON) -m pytest tests -q

test-fast:
	$(PYTHON) -m pytest tests --ignore=tests/functional -q

test-functional:
	$(PYTHON) -m pytest tests/functional -q

test-contracts:
	$(PYTHON) -m pytest tests/test_contracts.py -q

compile:
	$(PYTHON) -m compileall -q custom_components

reports:
	@mkdir -p reports
	$(PYTHON) -m pytest tests -q --junitxml=reports/pytest.xml
