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
	ln -sf $(VENV_PATH)/lib/$(shell basename $(PYTHON))/site-packages lib
	touch $(VENV)

lint: $(VENV)
	$(BIN)/flake8

_test: $(VENV)
	$(BIN)/py.test

run:
	DEVEL=1 $(BIN)/talisker tests.server:application --bind 0.0.0.0:8081 --reload

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
	rm $(VENV_PATH) lib -rf

clean-build:
	rm build/ dist/ .eggs/ -rf
	find . -name '*.egg-info' | xargs rm -rf
	find . -name '*.egg' | xargs rm -f

clean-pyc:
	find . -name '*.pyc' | xargs rm -f
	find . -name '*.pyo' | xargs rm -f
	find . -name '*~' | xargs rm -f
	find . -name '__pycache__' | xargs rm -rf

clean-test:
	rm .tox/ .coverage htmlcov/ -rf


# publishing
RELEASE_TOOLS = $(BIN)/twine $(BIN)/bumpversion
PY2ENV_PATH = .py2env
PY2ENV = $(PY2ENV_PATH)/.done
PACKAGE_NAME = $(shell $(PYTHON) setup.py --name)
PACKAGE_FULLNAME = $(shell $(PYTHON) setup.py --fullname)
PACKAGE_VERSION = $(shell $(PYTHON) setup.py --version)
RELEASE ?= patch
NEXT_VERSION = $(shell $(BIN)/bumpversion --allow-dirty --dry-run --list $(RELEASE) | grep new_version | cut -d'=' -f2)
CHANGELOG ?= HISTORY.rst

$(RELEASE_TOOLS): $(VENV)
	$(BIN)/pip install twine bumpversion

# minimal python2 env to build p2 wheel
$(PY2ENV):
	virtualenv $(PY2ENV_PATH) -p /usr/bin/python2.7
	$(PY2ENV_PATH)/bin/pip install wheel
	touch $@

# force build every time, it's not slow
_build: $(VENV) $(PY2ENV)
	rm -rf dist/*
	$(BIN)/python setup.py bdist_wheel sdist
	$(PY2ENV_PATH)/bin/python setup.py bdist_wheel

check-release: $(RELEASE_TOOLS)
	@grep $(NEXT_VERSION) $(CHANGELOG) || { echo "No entry for $(NEXT_VERSION) found in $(CHANGELOG)\nTry make changelog to add"; exit 1; }
	$(MAKE) tox

release: check-release
	@read -p "About to bump, tag and release $(PACKAGE_NAME) $(NEXT_VERSION), are you sure? [yn] " REPLY ; test "$$REPLY" = "y"
	$(BIN)/bumpversion $(RELEASE)
	$(MAKE) _build
	$(BIN)/twine upload dist/$(PACKAGE_NAME)-*

register: tox
	@read -p "About to regiser/update $(PACKAGE_NAME), are you sure? [yn] " REPLY ; test "$$REPLY" = "y"
	$(MAKE) _build
	$(BIN)/twine register dist/$(PACKAGE_NAME)-*

changelog: HEADER = $(NEXT_VERSION) ($(shell date +'%y-%m-%d'))
changelog: LENGTH = $(shell echo -n "$(HEADER)" | wc -c)
changelog: UNDERLINE = $(shell head -c $(LENGTH) < /dev/zero | tr '\0' '-')
changelog: ENTRY := $(shell mktemp -u)
changelog: GUARD := $(shell mktemp -u)
changelog:
	@echo "$(HEADER)\n$(UNDERLINE)\n\n* ..." >> $(ENTRY)
	@echo "## add your change log above, these lines will be stripped" >> $(ENTRY)
	@echo "## here are the commit messages since the last release:\n##" >> $(ENTRY)
	@git log v$(PACKAGE_VERSION)... --no-merges --decorate --format="##  %s" >> $(ENTRY)
	@touch $(GUARD)
	@$${EDITOR:-vi} $(ENTRY)
	@test $(ENTRY) -nt $(GUARD) && { grep -hv '^##' $(ENTRY) $(CHANGELOG) > $(GUARD) && mv -f $(GUARD) $(CHANGELOG) && echo "Updated $(CHANGELOG)"; } || echo "No changes, not updating $(CHANGELOG)"


# logstash testing
LOGSTASH_URL = https://download.elastic.co/logstash/logstash/logstash-2.3.4.tar.gz
LOGSTASH_CACHE = /tmp/$(shell basename $(LOGSTASH_URL))
LXC_NAME = logstash
LOGSTASH_DIR = /opt/logstash
LOGSTASH_CONFIG= talisker/logstash/test-config


$(LOGSTASH_CACHE):
	curl -o $(LOGSTASH_CACHE) $(LOGSTASH_URL)

logstash-setup: $(LOGSTASH_CACHE)
	-@lxc delete -f $(LXC_NAME)
	lxc launch ubuntu:trusty $(LXC_NAME) -c security.privileged=true
	sleep 5
	lxc file push $(LOGSTASH_CACHE) $(LXC_NAME)$(LOGSTASH_CACHE)
	lxc exec $(LXC_NAME) -- mkdir -p $(LOGSTASH_DIR)
	lxc exec $(LXC_NAME) -- apt install openjdk-7-jre-headless -y --no-install-recommends
	lxc exec $(LXC_NAME) -- tar xzf $(LOGSTASH_CACHE) -C $(LOGSTASH_DIR) --strip 1
	lxc config device add $(LXC_NAME) talisker disk source=$(PWD)/talisker/logstash path=/opt/logstash/patterns


.INTERMEDIATE: $(LOGSTASH_CONFIG)
.DELETE_ON_ERROR: $(LOGSTASH_CONFIG)
$(LOGSTASH_CONFIG):
	echo "input { stdin { type => talisker }}" > $(LOGSTASH_CONFIG)
	cat talisker/logstash/talisker.filter >> $(LOGSTASH_CONFIG)
	echo "output { stdout { codec => rubydebug }}" >> $(LOGSTASH_CONFIG)

logstash-test: $(LOGSTASH_CONFIG)
	cat tests/test.log | lxc exec $(LXC_NAME) -- $(LOGSTASH_DIR)/bin/logstash --quiet -f $(LOGSTASH_DIR)/patterns/$(shell basename $(LOGSTASH_CONFIG))

