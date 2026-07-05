# Mặc định period cho analytics targets (dùng period có data: 2013Q1 - 2014Q2)
period ?= 2014Q2

.PHONY: help validate up start stop restart down down-v build rebuild clean logs ps venv shell init-db test-conn shell-postgres psql notebook requirements-check ml-clustering ml-anomaly ml-decision ml-migration ml-early-warning ml snapshot analytics-kpi analytics-contribution analytics-drilldown analytics-causal analytics-runner analytics-all analytics etl-full

help:
	@echo "=== Data Warehouse & Analytics Project (Docker-first) ==="
	@echo ""
	@echo "--- Infrastructure ---"
	@echo "  make build     - build Docker images"
	@echo "  make up        - start containers (Postgres + MSSQL + ETL + Metabase)"
	@echo "  make down      - stop containers"
	@echo "  make down-v    - stop containers and remove volumes"
	@echo "  make start     - start existing stopped containers"
	@echo "  make stop      - stop running containers"
	@echo "  make restart   - restart containers"
	@echo "  make rebuild   - build images without cache"
	@echo "  make logs      - follow container logs"
	@echo "  make ps        - show container status"
	@echo ""
	@echo "--- Database ---"
	@echo "  make init-db   - create DW databases in PostgreSQL"
	@echo "  make restore-db - restore AdventureWorks to MSSQL"
	@echo "  make psql      - open psql inside Postgres container"
	@echo "  make shell-postgres - bash inside Postgres container"
	@echo ""
	@echo "--- ETL Pipeline ---"
	@echo "  make etl                - run ETL (incremental)"
	@echo "  make etl-full           - run ETL (full load)"
	@echo "  make test-conn          - test DB connections"
	@echo "  make validate           - validate config"
	@echo ""
	@echo "--- Machine Learning ---"
	@echo "  make ml             - run all ML modules"
	@echo "  make ml-clustering  - K-Means RFM segmentation"
	@echo "  make ml-anomaly     - Isolation Forest inventory anomaly"
	@echo "  make ml-migration   - Customer migration tracking"
	@echo "  make ml-early-warning - Early warning system"
	@echo "  make ml-decision    - Insight Engine (decision support)"
	@echo ""
	@echo "--- Analytics (chỉ dùng period có data: 2013Q1-2014Q2) ---"
	@echo "  make snapshot              - KPI snapshot"
	@echo "  make analytics-contribution period=2014Q2 - Contribution analysis"
	@echo "  make analytics-drilldown   period=2014Q2 - Drill-down diagnosis"
	@echo "  make analytics-causal      - Causal inference (Price Elasticity)"
	@echo "  make analytics-runner      period=2014Q2 - Run full analysis + generate report"
	@echo "  make analytics-all         period=2014Q2 - Run all analytics"
	@echo ""
	@echo "--- Utilities ---"
	@echo "  make shell     - bash inside ETL container"
	@echo "  make notebook  - start Jupyter Lab"
	@echo "  make clean     - stop containers and remove volumes"
	@echo "  make rebuild   - build images without cache"

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
	docker compose run --rm etl python scripts/validate_config.py

venv:
	@echo "Đã chuyển sang Docker-first. Dùng 'make shell' để vào container ETL."
	@docker compose build

shell:
	docker compose exec etl bash

init-db:
	docker compose cp scripts/init_db.sh postgres:/tmp/init_db.sh
	docker compose cp sql/ddl_script.sql postgres:/tmp/ddl_script.sql
	@set -a; \
	if [ -f .env ]; then . ./.env; fi; \
	set +a; \
	docker compose exec -u postgres postgres bash -c "export POSTGRES_HOST=localhost && export POSTGRES_USER=$${POSTGRES_USER:-postgres} && export POSTGRES_PASSWORD=$${POSTGRES_PASSWORD:-postgres} && bash /tmp/init_db.sh"

test-conn:
	docker compose exec etl python src/etl/etl.py --test

etl:
	docker compose exec etl python src/etl/etl.py

etl-full:
	docker compose exec etl python src/etl/etl.py --full

shell-postgres:
	docker compose exec postgres bash

psql:
	docker compose exec postgres psql -U "$${POSTGRES_USER:-postgres}" -d "$${POSTGRES_DB:-adventureworks}"

notebook:
	docker compose exec etl python -m jupyter lab --ip=0.0.0.0 --port=8888 --no-browser --notebook-dir=notebooks --allow-root

requirements-check:
	docker compose exec etl pip list --outdated

restore-db:
	bash scripts/restore_mssql.sh

ml-clustering:
	docker compose exec etl python src/ml/clustering.py

ml-anomaly:
	docker compose exec etl python src/ml/anomaly.py

ml-decision:
	docker compose exec etl python src/ml/decision_support.py

ml-migration:
	docker compose exec etl python src/ml/migration.py

ml-early-warning:
	docker compose exec etl python src/ml/early_warning.py

ml: ml-clustering ml-anomaly ml-migration ml-decision

snapshot:
	docker compose exec etl python src/etl/etl.py --snapshot

analytics-kpi:
	docker compose exec etl python src/etl/etl.py --analytics kpi --period $(period)

analytics-contribution:
	docker compose exec etl python src/etl/etl.py --analytics contribution --period $(period)

analytics-drilldown:
	docker compose exec etl python src/etl/etl.py --analytics drilldown --period $(period)

analytics-causal:
	docker compose exec etl python src/etl/etl.py --analytics causal

analytics-all:
	docker compose exec etl python src/etl/etl.py --analytics all --period $(period)

analytics-runner:
	docker compose exec etl python src/analytics/runner.py --period $(period)

analytics:
	@echo "Chạy 'make help' để xem danh sách analytics targets."
	@echo ""
	@echo "Lưu ý: AdventureWorks chỉ có data 2010-2014."
	@echo "Dùng period có data, vd:"
	@echo "  make analytics-contribution period=2014Q2"
	@echo "  make analytics-runner      period=2014Q2  # Báo cáo tổng hợp"
