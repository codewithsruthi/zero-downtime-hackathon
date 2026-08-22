.PHONY: setup test probe scrape heal approve demo demo-offline reset app doctor port-sync hydra-probe hydra-test hydra-demo hydra-amazon hydra-port hydra-port-amazon hydra-signoz hydra-dashboard hydra-dashboard-live vercel-build vercel-connect

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
	$(HYDRA_PY) scripts/hydra_demo.py

hydra-amazon:
	HYDRA_MODE=live $(HYDRA_PY) -m hydra scrape --source amazon_products

hydra-port:
	$(HYDRA_PY) scripts/hydra_bootstrap_port.py

hydra-port-amazon:
	$(HYDRA_PY) scripts/hydra_port_sync_amazon.py

hydra-signoz:
	$(HYDRA_PY) scripts/hydra_signoz_amazon.py

hydra-dashboard:
	HYDRA_MODE=replay HYDRA_DASHBOARD_CONTROLS=1 HYDRA_DASHBOARD_INTERVAL_S=3 HYDRA_DASHBOARD_HOLD_S=3.5 $(HYDRA_PY) -m hydra dashboard --watch

hydra-dashboard-live:
	HYDRA_DASHBOARD_CONTROLS=1 HYDRA_DASHBOARD_HOLD_S=3.5 $(HYDRA_PY) -m hydra dashboard-live --watch

vercel-build:
	node scripts/vercel-build.mjs

vercel-connect:
	node scripts/vercel-connect.mjs --deploy
