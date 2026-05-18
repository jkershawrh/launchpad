.PHONY: install test test-local lint clean dev-backend dev-frontend dev-admin demo-test

# Backend
install:
	pip install -e ".[dev]"

test:
	pytest -v --tb=short -m "not local"

test-all:
	pytest -v --tb=short

test-local:
	pytest -v --tb=short -m local

test-cov:
	pytest -v --cov=app --cov-report=term-missing

lint:
	ruff check backend/
	ruff format --check backend/

format:
	ruff format backend/

# Partner Portal (frontend/)
frontend-install:
	cd frontend && npm install

frontend-build:
	cd frontend && npm run build

# Admin App (admin/)
admin-install:
	cd admin && npm install

admin-build:
	cd admin && npm run build

# Demo stack (podman-compose)
demo-up:
	cd demos && python3 -m podman_compose up -d

demo-down:
	cd demos && python3 -m podman_compose down

demo-test:
	cd demos && python3 -m pytest tests/ -v --tb=short

# Dev servers
dev-backend:
	cd backend && python3 -m uvicorn app.main:app --reload --port 8000

dev-backend-local:
	cd backend && LAUNCHPAD_MODE=local python3 -m uvicorn app.main:app --reload --port 8000

dev-frontend:
	cd frontend && npm run dev

dev-admin:
	cd admin && npm run dev

# Clean
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache *.egg-info build dist
	rm -rf frontend/dist admin/dist
