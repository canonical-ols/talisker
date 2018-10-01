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
export STATSD_DSN=udp://localhost:8125

VENV_PATH = env
VENV = $(VENV_PATH)/ready
BIN = $(VENV_PATH)/bin
PY3 = $(shell which python3)
PYTHON ?= $(shell readlink -f $(PY3))
TALISKER_EXTRAS=flask,django,celery,prometheus,pg,dev
LIMBO_REQUIREMENTS=tests/requirements.limbo.txt

default: test

$(VENV_PATH):
	virtualenv $(VENV_PATH) -p $(PYTHON)

setup.py: setup.cfg build_setup.py | $(VENV_PATH)
	env/bin/python build_setup.py > setup.py

$(LIMBO_REQUIREMENTS): setup.cfg limbo.py | $(VENV_PATH)
	env/bin/python limbo.py --extras=$(TALISKER_EXTRAS) > $(LIMBO_REQUIREMENTS)

# workaround to allow tox to build limbo requirements on demand
limbo-env: $(LIMBO_REQUIREMENTS)
	pip install $(TOX_OPTS) -r requirements.limbo.text $(TOX_PACKAGES)

$(VENV): setup.py requirements.tests.txt requirements.devel.txt | $(VENV_PATH)
	$(BIN)/pip install -e .[$(TALISKER_EXTRAS)]
	$(BIN)/pip install -r requirements.devel.txt
	ln -sf $(VENV_PATH)/lib/$(shell basename $(PYTHON))/site-packages lib
	touch $(VENV)

lint: $(VENV)
	$(BIN)/flake8 talisker tests

_test: $(VENV)
	. $(BIN)/activate && $(BIN)/pytest --tb=short -n auto $(ARGS)

TEST_FILES = $(shell find tests -maxdepth 1 -name test_\*.py  | cut -c 7- | cut -d. -f1)
$(TEST_FILES): $(VENV)
	. $(BIN)/activate && py.test -k $@ $(ARGS)

export DEBUGLOG=log
export DEVEL=1
WORKER ?= sync
PORT ?= 8000
TALISKER = $(BIN)/talisker.gunicorn --bind 0.0.0.0:$(PORT) --reload --worker-class $(WORKER) $(ARGS)
run wsgi:
	$(TALISKER) tests.wsgi_app:application

run_multiprocess: ARGS=-w4
run_multiprocess: run

lib/sqlalchemy:
	$(BIN)/pip install sqlalchemy

flask: | lib/sqlalchemy
	$(TALISKER) tests.flask_app:app

lib/redis:
	$(BIN)/pip install redis

db-setup:
	psql -U postgres -c "create user django_app with password 'django_app';"
	psql -U postgres -c "create database django_app owner django_app;"

migrate:
	$(BIN)/python tests/django_app/manage.py migrate

celery-worker: lib/redis
	$(BIN)/talisker.celery worker -q -A tests.celery_app

celery-client: lib/redis
	$(BIN)/python tests/celery_app.py

django: lib/redis
	PYTHONPATH=tests/django_app/ $(TALISKER) tests.django_app.django_app.wsgi:application

django-celery: lib/redis
	PYTHONPATH=tests/django_app/ $(BIN)/talisker.celery worker -q -A django_app

statsd:
	$(BIN)/python tests/udpecho.py

lib/sparklines/sparklines.py:
	$(BIN)/pip install sparklines

show-prometheus: HOST?=localhost:8000
show-prometheus: lib/sparklines/sparklines.py
	$(BIN)/python scripts/metrics.py http://$(HOST)/_status/metrics

test: _test lint

debug-test:
	. $(BIN)/activate && $(BIN)/pytest -s --pdb $(ARGS)

tox: $(VENV) $(LIMBO_REQUIREMENTS)
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
	rm .tox/ .pytest_cache .coverage htmlcov/ results logstash-test-results tests/requirements.limbo.txt -rf 


# publishing
RELEASE_TOOLS = $(BIN)/twine $(BIN)/bumpversion
PY2ENV_PATH = .py2env
PY2ENV = $(PY2ENV_PATH)/.done
PACKAGE_NAME = $(shell $(BIN)/python setup.py --name)
PACKAGE_FULLNAME = $(shell $(BIN)/python setup.py --fullname)
PACKAGE_VERSION = $(shell $(BIN)/python setup.py --version)
RELEASE ?= patch
NEXT_VERSION = $(shell $(BIN)/bumpversion --allow-dirty --dry-run --list $(RELEASE) | grep new_version | cut -d'=' -f2)
CURRENT_VERSION = $(shell $(BIN)/python setup.py --version)
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

release-check: $(RELEASE_TOOLS)
	git checkout master
	git pull
	@grep $(NEXT_VERSION) $(CHANGELOG) || { echo "No entry for $(NEXT_VERSION) found in $(CHANGELOG)\nTry make changelog to add"; exit 1; }
	git tag | grep -q v$(NEXT_VERSION) && { echo "Tag v$(NEXT_VERSION) already exists!"; exit 1; } || true
	test -z "$(SKIP_TOX)" && $(MAKE) tox

release-build: TAG=v$(NEXT_VERSION)
release-build: $(RELEASE_TOOLS)
	@read -p "About to bump $(PACKAGE_NAME) to $(NEXT_VERSION) and build $(PACKAGE_NAME) $(NEXT_VERSION), are you sure? [yn] " REPLY ; test "$$REPLY" = "y"
	$(BIN)/bumpversion $(RELEASE)
	$(MAKE) setup.py
	$(MAKE) _build

release-pypi: $(RELEASE_TOOLS)
	$(BIN)/twine upload dist/$(PACKAGE_NAME)-*
	git add setup.py setup.cfg talisker/__init__.py docs/conf.py
	git commit -m 'bumping to version $(CURRENT_VERSION)'
	git tag

register: tox
	@read -p "About to register/update $(PACKAGE_NAME), are you sure? [yn] " REPLY ; test "$$REPLY" = "y"
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
LOGSTASH_URL = https://download.elastic.co/logstash/logstash/logstash-2.0.0.tar.gz
LOGSTASH_CACHE = /tmp/$(shell basename $(LOGSTASH_URL))
LXC_NAME = logstash
LOGSTASH_DIR = /opt/logstash
LOGSTASH_CONFIG= talisker/logstash/test-config
LOGSTASH_CONFIG_LXC=$(LOGSTASH_DIR)/patterns/$(shell basename $(LOGSTASH_CONFIG))
LOGSTASH_PATTERNS_LXC=$(LOGSTASH_DIR)/patterns
LOGSTASH_RESULTS=test-results
LOGSTASH=lxc exec $(LXC_NAME) -- $(LOGSTASH_DIR)/bin/logstash -f $(LOGSTASH_CONFIG_LXC)


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
	lxc config device add $(LXC_NAME) talisker disk source=$(PWD)/talisker/logstash path=$(LOGSTASH_PATTERNS_LXC)


define REPORT_PY
import sys, json
for line in sys.stdin:
    r = json.loads(line)
    if 'tags' in r:
        if '_grokparsefailure' in r['tags'] or '_rubyexception' in r['tags']:
            print(json.dumps(r, sort_keys=True, indent=4, separators=(',', ': ')))
endef
export REPORT_PY

define CONFIG
input { stdin { type => talisker }}
output { 
    file { 
       path => "$(LOGSTASH_PATTERNS_LXC)/$(LOGSTASH_RESULTS)"
       codec => json_lines
    }
}
endef
export CONFIG


$(LOGSTASH_CONFIG): talisker/logstash/talisker.filter
	echo "$$CONFIG" > $(LOGSTASH_CONFIG)
	cat talisker/logstash/talisker.filter >> $(LOGSTASH_CONFIG)

logstash-check: $(LOGSTASH_CONFIG)
	$(LOGSTASH) -t

logstash-test: $(LOGSTASH_CONFIG)
	rm talisker/logstash/$(LOGSTASH_RESULTS) -f
	cat tests/test.log | grep -v '^#' | $(LOGSTASH) --quiet
	cat talisker/logstash/$(LOGSTASH_RESULTS) | python -c "$$REPORT_PY"

logstash-test-truncate: $(LOGSTASH_CONFIG)
	sed -i 's/20000/100/' $(LOGSTASH_CONFIG)
	rm talisker/logstash/$(LOGSTASH_RESULTS) -f
	cat tests/test_truncate.log | grep -v '^#' | $(LOGSTASH) --quiet
	cat talisker/logstash/$(LOGSTASH_RESULTS) | jq
	rm $(LOGSTASH_CONFIG)

logstash-show:
	cat talisker/logstash/$(LOGSTASH_RESULTS) | jq
