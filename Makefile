.PHONY: install lint format typecheck test check migrate upgrade

install:
	uv sync

lint:
	uv run ruff check src tests

format:
	uv run ruff format src tests

typecheck:
	uv run mypy src

test:
	uv run pytest -v

check:
	uv run ruff check src tests
	uv run ruff format --check src tests
	uv run mypy src
	uv run pytest -v

upgrade:
	uv run alembic upgrade head

migrate:
	uv run alembic revision --autogenerate -m "$(m)"