# NOA — common dev targets
.PHONY: dev dev-workers deps migrate smoke docker-up docker-down start

# Auto-load .env file if it exists
ifneq (,$(wildcard ./.env))
  include .env
  export
endif

start: deps
	@echo "Stopping any previous NOA processes..."
	-@lsof -ti :8000 | xargs kill -9 2>/dev/null || true
	-@lsof -ti :3000 | xargs kill -9 2>/dev/null || true
	-@pkill -f "arq noa_api" 2>/dev/null || true
	@sleep 1
	@echo "Starting NOA (requires Docker Desktop running)..."
	docker compose up -d
	@echo "Waiting for Postgres..."
	python scripts/wait_for_db.py
	alembic -c db/alembic.ini upgrade head
	@echo "Launching API, worker, and web..."
	(cd apps/api && uvicorn noa_api.main:app --reload) & \
	(cd apps/api && python -m arq noa_api.worker.WorkerSettings) & \
	(cd apps/web && npm run dev) & \
	wait

deps:
	cd apps/web && npm install
	pip install -e packages/contracts/python
	pip install -e "apps/api[dev]"

docker-up:
	docker compose up -d

docker-down:
	docker compose down

migrate:
	alembic -c db/alembic.ini upgrade head

dev-workers:
	@echo "Run workers manually: cd apps/api && arq noa_api.worker.WorkerSettings"
	@echo "Or: python -m arq noa_api.worker.WorkerSettings"

smoke:
	python scripts/smoke_test.py

dev:
	@echo "Terminal 1: docker compose up -d && make migrate"
	@echo "Terminal 2: cd apps/api && uvicorn noa_api.main:app --reload"
	@echo "Terminal 3: npm run dev (from repo root for web)"
