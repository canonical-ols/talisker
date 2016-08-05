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
	$(BIN)/pip install -r devel_requirements.txt
	ln -sf $(VENV_PATH)/lib/$(PYTHON)/site-packages lib
	touch $(VENV)

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


VERSION = $(shell $(PYTHON) setup.py --version)
PY2WHEEL = dist/talisker-$(VERSION)-py2-none-any.whl
PY3WHEEL = dist/talisker-$(VERSION)-py3-none-any.whl

$(PY2WHEEL):
	python2.7 setup.py bdist_wheel

$(PY3WHEEL):
	$(PYTHON) setup.py bdist_wheel

wheels: $(PY2WHEEL) $(PY3WHEEL)


register: $(PY2WHEEL) $(PY3WHEEL)
	env/bin/twine register $^

publish: $(PY2WHEEL) $(PY3WHEEL)
	env/bin/twine upload $^
