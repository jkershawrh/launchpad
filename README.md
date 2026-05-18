# Partner AI Launchpad

Reusable OpenShift-based lab platform for Red Hat/Intel partner and client demos.

Provides three experiences:
- **Quick Start Labs** — prebuilt, guided, fast-start demos
- **Guided Build Areas** — template-driven build spaces for AI ideas
- **Open Sandboxes** — flexible partner/client namespaces with quotas, tools, and observability

## Local Setup

```bash
# Python 3.11+ required
pip install -e ".[dev]"
```

## Run Tests

```bash
make test
```

## Run Tests with Coverage

```bash
make test-cov
```

## Project Structure

```
backend/
  app/
    domain/       # Pydantic models, enums, lifecycle state machine
    adapters/     # External system adapter interfaces
    services/     # Business logic orchestration
  tests/          # pytest test suite

fixtures/         # Seed data (YAML)
schemas/          # JSON Schema definitions
docs/             # Architecture and design docs
```

## Stack

- **Backend:** Python, FastAPI, Pydantic
- **Database:** PostgreSQL (Phase 3)
- **Frontend:** React, Vite, Tailwind (Phase 5)
- **Tests:** pytest, Vitest
