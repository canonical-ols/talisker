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
ENV = env

default: test

$(ENV):
	virtualenv $(ENV) -p /usr/bin/python3
	$(ENV)/bin/pip install -U pip
	$(ENV)/bin/pip install -e .[devel]

lint: | $(ENV)
	$(ENV)/bin/flake8 talisker tests setup.py

test: lint 
	$(ENV)/bin/py.test

detox: | $(ENV)
	$(ENV)/bin/detox

coverage: | $(ENV)
	$(ENV)/bin/coverage run --source talisker $(ENV)/bin/py.test
	$(ENV)/bin/coverage report -m
	$(ENV)/bin/coverage html
	$(BROWSER) htmlcov/index.html

docs: | $(ENV)
	rm -f docs/talisker.rst
	rm -f docs/modules.rst
	$(ENV)/bin/sphinx-apidoc -o docs/ talisker
	$(MAKE) -C docs clean
	$(MAKE) -C docs html
	$(BROWSER) docs/_build/html/index.html

clean: clean-build clean-pyc clean-test
	rm -rf $(ENV)

clean-build:
	rm -fr build/
	rm -fr dist/
	rm -fr .eggs/
	find . -name '*.egg-info' -exec rm -fr {} +
	find . -name '*.egg' -exec rm -f {} +

clean-pyc:
	find . -name '*.pyc' -exec rm -f {} +
	find . -name '*.pyo' -exec rm -f {} +
	find . -name '*~' -exec rm -f {} +
	find . -name '__pycache__' -exec rm -fr {} +

clean-test:
	rm -fr .tox/
	rm -f .coverage
	rm -fr htmlcov/


