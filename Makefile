.PHONY: help validate up start stop restart down down-v build rebuild clean logs ps venv shell init-db test-conn shell-postgres psql notebook requirements-check

help:
	@echo "Targets:"
	@echo "  make validate  - check configuration before running"
	@echo "  make up        - start containers in detached mode"
	@echo "  make start     - start existing stopped containers"
	@echo "  make stop      - stop running containers"
	@echo "  make restart   - restart containers"
	@echo "  make down      - stop containers"
	@echo "  make down-v    - stop containers and remove volumes"
	@echo "  make build     - build images"
	@echo "  make rebuild   - build images without cache"
	@echo "  make clean     - stop containers and remove volumes"
	@echo "  make logs      - follow container logs"
	@echo "  make ps        - show container status"
	@echo "  make venv      - create virtualenv and install Python deps"
	@echo "  make shell     - enter virtualenv shell (no need for 'source')"
	@echo "  make init-db   - create databases if missing"
	@echo "  make test-conn - test Postgres connection from Python"
	@echo "  make shell-postgres - open a shell inside Postgres container"
	@echo "  make psql      - open psql inside Postgres container"
	@echo "  make notebook  - start Jupyter Lab"
	@echo "  make requirements-check - check for outdated packages"

up:
	docker compose up -d

start:
	docker compose start

stop:
	docker compose stop

restart:
	docker compose restart

down:
	docker compose down

down-v:
	docker compose down -v

clean:
	docker compose down -v

build:
	docker compose build

rebuild:
	docker compose build --no-cache

logs:
	docker compose logs -f

ps:
	docker compose ps

validate:
	python3 scripts/validate_config.py

venv:
	bash scripts/create_venv.sh

shell:
	@echo "===================================================================="
	@echo "ĐANG VÀO MÔI TRƯỜNG ẢO PYTHON (VIRTUALENV)"
	@echo "Để THOÁT ra ngoài terminal thường, hãy gõ: exit"
	@echo "===================================================================="
	@bash -c 'source .venv/bin/activate && bash'

init-db:
	@set -a; \
	if [ -f .env ]; then . ./.env; fi; \
	set +a; \
	export POSTGRES_HOST=localhost; \
	bash scripts/init_db.sh

test-conn:
	@set -a; \
	if [ -f .env ]; then . ./.env; fi; \
	set +a; \
	export POSTGRES_HOST=localhost; \
	.venv/bin/python -m src.etl

etl:
	@set -a; \
	if [ -f .env ]; then . ./.env; fi; \
	set +a; \
	export POSTGRES_HOST=localhost; \
	.venv/bin/python src/etl.py

shell-postgres:
	docker compose exec postgres bash

psql:
	docker compose exec postgres psql -U "$${POSTGRES_USER:-postgres}" -d "$${POSTGRES_DB:-adventureworks}"

notebook:
	.venv/bin/python -m jupyter lab --notebook-dir=notebooks

requirements-check:
	bash -c 'source .venv/bin/activate && pip list --outdated'
