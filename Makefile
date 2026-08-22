.PHONY: setup test probe scrape heal approve demo demo-offline reset app doctor port-sync

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
