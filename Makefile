.PHONY: install run test lint typecheck security openapi build clean lock migrate

PYTHON ?= .venv/bin/python
PIP_AUDIT ?= $(PYTHON) -m pip_audit

install:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -e ".[dev]"

run:
	$(PYTHON) backend/app.py

test:
	$(PYTHON) -m pytest tests/ -q --tb=short

lint:
	$(PYTHON) -m ruff check backend tests

typecheck:
	$(PYTHON) -m mypy backend

security:
	$(PIP_AUDIT)

openapi:
	$(PYTHON) scripts/export_openapi.py

build:
	$(PYTHON) -m build

clean:
	find . -type d \( -name __pycache__ -o -name .pytest_cache -o -name .ruff_cache \) -prune -exec rm -rf {} +

lock:
	$(PYTHON) -m pip freeze > requirements.lock

migrate:
	$(PYTHON) -m alembic upgrade head
