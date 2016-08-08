.PHONY: clean-pyc clean-build docs clean
.SUFFIXES:
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
PY3 = $(shell which python3)
PYTHON ?= $(shell readlink -f $(PY3))

default: test

$(VENV):
	virtualenv $(VENV_PATH) -p $(PYTHON)
	$(BIN)/pip install -U pip
	$(BIN)/pip install -e .
	$(BIN)/pip install -r requirements.devel.txt
	touch $(VENV)

lib: 
	ln -sf $(VENV_PATH)/lib/$(basename $(PYTHON))/site-packages lib

lint: $(VENV)
	$(BIN)/flake8 talisker tests setup.py

_test: $(VENV)
	$(BIN)/py.test

run:
	$(BIN)/talisker tests.server:application --bind 0.0.0.0:8081

test: _test lint

tox testall: $(VENV)
	$(BIN)/tox

detox: $(VENV)
	$(BIN)/detox

coverage: $(VENV)
	$(BIN)/coverage run --source talisker $(BIN)/py.test
	$(BIN)/coverage report -m
	$(BIN)/coverage html
	$(BROWSER) htmlcov/index.html

docs: $(VENV)
	@rm -f docs/talisker.rst
	@rm -f docs/modules.rst
	$(BIN)/sphinx-apidoc -o docs/ talisker
	$(MAKE) -C docs clean SPHINXBUILD=../$(BIN)/sphinx-build
	$(MAKE) -C docs html SPHINXBUILD=../$(BIN)/sphinx-build

view:
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

# publishing

-include .wheels.mk
.wheels.mk: NAME = $(shell $(PYTHON) setup.py --name)
.wheels.mk: VERSION = $(shell $(PYTHON) setup.py --version)
.wheels.mk: setup.py talisker/__init__.py
	echo "PY2WHEEL = dist/$(NAME)-$(VERSION)-py2-none-any.whl" > $@
	echo "PY3WHEEL = dist/$(NAME)-$(VERSION)-py3-none-any.whl" >> $@

RELEASE_TOOLS= $(BIN)/twine $(BIN)/bumpversion

$(RELEASE_TOOLS) release-tools: $(VENV)
	$(BIN)/pip install -r requirements.release.txt

.checkdocs: $(RELEASE_TOOLS) README.rst HISTORY.rst
	$(BIN)/python setup.py checkdocs
	touch $@

$(PY2WHEEL): .checkdocs
	python2.7 setup.py bdist_wheel

$(PY3WHEEL): .checkdocs
	$(PYTHON) setup.py bdist_wheel

wheels: talisker/ setup.py README.rst HISTORY.rst $(PY2WHEEL) $(PY3WHEEL)

register: wheels
	$(BIN)/twine register $(PY3WHEEL)

publish: wheels
	$(BIN)/twine upload $(PY2WHEEL)
	$(BIN)/twine upload $(PY3WHEEL)
