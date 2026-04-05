.PHONY: help up down build logs ps clean reset

# Default target
help:
	@echo ""
	@echo "  QuantLab Platform - Commands"
	@echo "  =================================="
	@echo ""
	@echo "  make up          - Start all services"
	@echo "  make up-core     - Start core services only (DB, Redis, Backend, Frontend)"
	@echo "  make down        - Stop all services"
	@echo "  make build       - Rebuild all Docker images"
	@echo "  make logs        - Follow logs (all services)"
	@echo "  make ps          - Show running services"
	@echo "  make clean       - Remove containers and volumes"
	@echo "  make reset       - Full reset (WARNING: deletes all data)"
	@echo ""
	@echo "  Service URLs:"
	@echo "  - Frontend:    http://localhost:3000"
	@echo "  - API:         http://localhost:8000"
	@echo "  - API Docs:    http://localhost:8000/docs"
	@echo "  - MLflow:      http://localhost:5000"
	@echo "  - Jupyter:     http://localhost:8888"
	@echo "  - Flower:      http://localhost:5555"
	@echo "  - Grafana:     http://localhost:3001"
	@echo "  - MinIO:       http://localhost:9001"
	@echo ""

# Setup
setup:
	@cp -n .env.example .env 2>/dev/null || true
	@mkdir -p research/notebooks research/data
	@echo "Setup complete. Edit .env before starting."

# Start everything
up:
	@docker compose up -d
	@echo ""
	@echo "All services started!"
	@echo "Frontend: http://localhost:3000"
	@echo "API Docs: http://localhost:8000/docs"

# Start core services only
up-core:
	@docker compose up -d postgres redis backend frontend worker-backtest beat
	@echo "Core services started."

# Stop
down:
	@docker compose down

# Build
build:
	@docker compose build --parallel

# Build no cache
build-fresh:
	@docker compose build --no-cache --parallel

# Logs
logs:
	@docker compose logs -f

logs-%:
	@docker compose logs -f $*

# Status
ps:
	@docker compose ps

# Database migrations
migrate:
	@docker compose exec backend alembic upgrade head

# Open backend shell
shell-backend:
	@docker compose exec backend bash

# Open DB shell
shell-db:
	@docker compose exec postgres psql -U ${POSTGRES_USER:-quant} -d ${POSTGRES_DB:-quantdb}

# Run backtest via CLI
backtest:
	@docker compose exec backend python -m app.cli backtest $(ARGS)

# Clean (keep volumes)
clean:
	@docker compose down --remove-orphans

# Full reset - WARNING: deletes all data
reset:
	@echo "WARNING: This will delete all data. Press Ctrl+C to cancel..."
	@sleep 5
	@docker compose down -v --remove-orphans
	@docker system prune -f
	@echo "Reset complete."
