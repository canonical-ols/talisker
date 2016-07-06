.PHONY: clean-pyc clean-build docs clean
define BROWSER_PYSCRIPT
import os, webbrowser, sys
try:
	from urllib import pathname2url
except:
	from urllib.request import pathname2url

webbrowser.open("file://" + pathname2url(os.path.abspath(sys.argv[1])))
endef
export BROWSER_PYSCRIPT
BROWSER := python -c "$$BROWSER_PYSCRIPT"

VENV_PATH = env
VENV = $(VENV_PATH)/ready
BIN = $(VENV_PATH)/bin
PYTHON ?= python3

default: test
.ONESHELL:
.SUFFIXES:

$(VENV):
	virtualenv $(VENV_PATH) -p /usr/bin/$(PYTHON)
	$(BIN)/pip install -U pip
	$(BIN)/pip install -e .
	$(BIN)/pip install -r devel_requirements.txt
	ln -sf $(VENV_PATH)/lib/$(PYTHON)/site-packages lib
	touch $(VENV)

lint: $(VENV)
	$(BIN)/flake8 talisker tests setup.py

_test: $(VENV)
	$(BIN)/py.test

run:
	$(BIN)/python tests/server.py

test: _test lint

wheel:
	$(BIN)/python setup.py bdist_wheel

detox: $(VENV)
	$(BIN)/detox

coverage: $(VENV)
	$(BIN)/coverage run --source talisker $(BIN)/py.test
	$(BIN)/coverage report -m
	$(BIN)/coverage html
	$(BROWSER) htmlcov/index.html

docs: $(VENV)
	rm -f docs/talisker.rst
	rm -f docs/modules.rst
	$(BIN)/sphinx-apidoc -o docs/ talisker
	$(MAKE) -C docs clean
	$(MAKE) -C docs html
	$(BROWSER) docs/_build/html/index.html

clean: clean-build clean-pyc clean-test
	rm -rf $(VENV_PATH) lib

clean-build:
	rm -fr build/
	rm -fr dist/
	rm -fr .eggs/
	find . -name '*.egg-info' | xargs rm -rf
	find . -name '*.egg' | xargs rm -f

clean-pyc:
	find . -name '*.pyc' | xargs rm -f
	find . -name '*.pyo' | xargs rm -f
	find . -name '*~' | xargs rm -f
	find . -name '__pycache__' | xargs rm -rf

clean-test:
	rm -fr .tox/
	rm -f .coverage
	rm -fr htmlcov/
