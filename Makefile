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
TALISKER_EXTRAS=flask,django,celery,prometheus,dev
LIMBO_REQUIREMENTS=requirements.limbo.txt
export VENV_BIN=$(BIN)

default: test

TALISKER_EXTRAS=flask,django,celery,prometheus,dev
$(VENV_PATH):
	virtualenv $(VENV_PATH) -p $(PYTHON)

setup.py: setup.cfg build_setup.py | $(VENV_PATH)
	env/bin/python build_setup.py > setup.py

$(LIMBO_REQUIREMENTS): setup.cfg limbo.py | $(VENV_PATH)
	env/bin/python limbo.py --extras=$(TALISKER_EXTRAS) > $(LIMBO_REQUIREMENTS)

$(VENV): setup.py $(LIMBO_REQUIREMENTS) | $(VENV_PATH)
	$(BIN)/pip install -U pip
	$(BIN)/pip install -e .[$(TALISKER_EXTRAS)]
	$(BIN)/pip install -r requirements.devel.txt
	ln -sf $(VENV_PATH)/lib/$(shell basename $(PYTHON))/site-packages lib
	touch $(VENV)

lint: $(VENV)
	$(BIN)/flake8 talisker tests setup.py

_test: $(VENV)
	$(BIN)/py.test $(ARGS)

export DEBUGLOG=log
TALISKER = $(BIN)/talisker --bind 0.0.0.0:8081 --reload $(ARGS)
run wsgi:
	$(TALISKER) tests.wsgi_app:application

run_multiprocess: ARGS=-w4
run_multiprocess: run

flask:
	$(TALISKER) tests.flask_app:app

lib/redis:
	$(BIN)/pip install redis

DJANGO_DB = tests/django_app/db.sqlite3
$(DJANGO_DB) migrate:
	$(BIN)/python tests/django_app/manage.py migrate

celery-worker: lib/redis
	$(BIN)/talisker.celery worker -q -A tests.celery_app

celery-client: lib/redis
	$(BIN)/python tests/celery_app.py

django: lib/redis $(DJANGO_DB)
	PYTHONPATH=tests/django_app/ $(TALISKER) tests.django_app.django_app.wsgi:application

django-celery: lib/redis $(DJANGO_DB)
	PYTHONPATH=tests/django_app/ $(BIN)/talisker.celery worker -q -A django_app

statsd:
	$(BIN)/python tests/udpecho.py

test: _test lint

tox: $(VENV)
	$(BIN)/tox $(ARGS)

coverage: $(VENV)
	$(BIN)/py.test --cov=talisker --cov-report html:htmlcov --cov-report term
	$(BROWSER) htmlcov/index.html

docs: $(VENV)
	$(MAKE) -C docs clean SPHINXBUILD=../$(BIN)/sphinx-build
	$(MAKE) -C docs html SPHINXBUILD=../$(BIN)/sphinx-build SPHINXOPTS=-W

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
	rm .tox/ .coverage htmlcov/ results -rf


# publishing
RELEASE_TOOLS = $(BIN)/twine $(BIN)/bumpversion
PY2ENV_PATH = .py2env
PY2ENV = $(PY2ENV_PATH)/.done
PACKAGE_NAME = $(shell $(BIN)/python setup.py --name)
PACKAGE_FULLNAME = $(shell $(BIN)/python setup.py --fullname)
PACKAGE_VERSION = $(shell $(BIN)/python setup.py --version)
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
	git checkout master
	git pull
	@grep $(NEXT_VERSION) $(CHANGELOG) || { echo "No entry for $(NEXT_VERSION) found in $(CHANGELOG)\nTry make changelog to add"; exit 1; }
	$(MAKE) tox

release: check-release
	@read -p "About to bump, tag and release $(PACKAGE_NAME) $(NEXT_VERSION), are you sure? [yn] " REPLY ; test "$$REPLY" = "y"
	$(BIN)/bumpversion $(RELEASE)
	$(MAKE) _build
	$(BIN)/twine upload dist/$(PACKAGE_NAME)-*
	git push --tags

register: tox
	@read -p "About to regiser/update $(PACKAGE_NAME), are you sure? [yn] " REPLY ; test "$$REPLY" = "y"
	$(MAKE) _build
	$(BIN)/twine register dist/$(PACKAGE_NAME)-*

changelog: HEADER = $(NEXT_VERSION) ($(shell date +'%Y-%m-%d'))
changelog: LENGTH = $(shell echo -n "$(HEADER)" | wc -c)
changelog: UNDERLINE = $(shell head -c $(LENGTH) < /dev/zero | tr '\0' '-')
changelog: ENTRY := $(shell mktemp -u)
changelog: GUARD := $(shell mktemp -u)
changelog: $(RELEASE_TOOLS)
	@echo "$(HEADER)\n$(UNDERLINE)\n\n* ...\n" >> $(ENTRY)
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
	sleep 10
	lxc file push $(LOGSTASH_CACHE) $(LXC_NAME)$(LOGSTASH_CACHE)
	lxc exec $(LXC_NAME) -- mkdir -p $(LOGSTASH_DIR)
	lxc exec $(LXC_NAME) -- apt update
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

