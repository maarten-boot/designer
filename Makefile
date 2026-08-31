# Designer — the checks, in one place.
#
# `make check` is what to run before believing anything works. It is four
# separate nets and they catch different things:
#
#   lint   style, unused names, and the constructs ruff knows are traps
#   types  attribute and call errors — the ones that survive a green test run
#          because the widget half of the suite skips without a display
#   test   behaviour, including the widget tests where there is a display
#   model  the worked example: does it load, round trip, and check clean
#
# The third of these is the one that lies most easily. On a machine with no
# tkinter every widget test skips and the suite still reports success, so `make
# types` is not optional there.

PACKAGES := packages/designer-model/src:packages/designer-app/src
PY       := PYTHONPATH=$(PACKAGES) python3
EXAMPLE  := examples/sales.json
EXAMPLE  := ../sales.json

.DEFAULT_GOAL := help
.PHONY: help deps format lint types test gui model docs check run clean dist

help:  ## show this list
	@grep -E '^[a-z]+:.*?## ' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "} {printf "  %-8s %s\n", $$1, $$2}'

deps:  ## install the development tools
	pip install pytest ruff mypy

format:  ## rewrite the source in the house style
	ruff format packages tools

lint:  ## style and the traps ruff knows about
	ruff check packages tools

types:  ## attribute and call errors a passing test run can hide
	mypy --config-file mypy.ini

test:  ## the whole suite; widget tests skip without a display
	$(PY) -m pytest packages -q

gui:  ## only the tests that build a real window
	$(PY) -m pytest packages/designer-app/tests/test_widgets.py -v

model:  ## load, round trip and check the worked example
	$(PY) tools/check_model.py $(EXAMPLE)

docs:  ## the documents against each other and against the code
	$(PY) tools/check_docs.py

check: lint types test model docs  ## everything above, in the order that fails fastest

run:  ## open the worked example
	$(PY) -m designer_app.main $(EXAMPLE)

dist:  ## regenerate the built-in library and the operator matrix
# examples/sales.json is not regenerated: the tool that built it is gone, and
# this target used to call it with the failure swallowed. The example is
# maintained as a file and held to account by `make model` instead.
	$(PY) tools/build_stdlib.py
	$(PY) tools/build_matrix.py

clean:  ## remove caches
	find . -type d \( -name __pycache__ -o -name .pytest_cache -o -name .ruff_cache \
		-o -name .mypy_cache \) -prune -exec rm -rf {} +
