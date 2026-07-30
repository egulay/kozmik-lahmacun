.PHONY: setup up down reset smoke config test start-all stop-all demo-data acceptance

setup:
	./scripts/setup-env.sh

up:
	./scripts/dev-up.sh

down:
	./scripts/dev-down.sh

reset:
	./scripts/dev-down.sh --volumes

smoke:
	./scripts/smoke-test.sh

config:
	./scripts/verify-static.sh

test:
	./scripts/test-all.sh

start-all:
	./scripts/start-all.sh

stop-all:
	./scripts/stop-all.sh

demo-data:
	./scripts/seed-demo-data.sh

acceptance:
	./scripts/demo-acceptance.sh
