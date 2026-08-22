.PHONY: setup test probe scrape heal approve demo demo-offline reset app doctor port-sync hydra-probe hydra-test hydra-demo

setup:
	./scripts/setup.sh

test:
	npm test

probe:
	./scripts/probe.sh

scrape:
	./scripts/scrape.sh

heal:
	./scripts/heal.sh

approve:
	./bin/factory approve

demo:
	./scripts/demo.sh

demo-offline:
	FACTORY_MODE=replay ./scripts/demo.sh

reset:
	./scripts/reset.sh

app:
	node --import ./app/instrumentation.js app/server.js

doctor:
	./bin/factory doctor

port-sync:
	./bin/factory port-sync

HYDRA_PY ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,/usr/bin/python3)

hydra-probe:
	$(HYDRA_PY) scripts/hydra_probe.py

hydra-test:
	$(HYDRA_PY) -m pytest tests/hydra -q

hydra-demo:
	HYDRA_MODE=replay $(HYDRA_PY) -m hydra demo
