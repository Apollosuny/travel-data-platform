.PHONY: install lint format typecheck test check migrate upgrade github-env-init github-env-push github-env-dry-run

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

STAGE ?= prod

github-env-init:
	uv run python -m travel_data_platform.deployment.setup_github_env --init $(STAGE)

github-env-dry-run:
	uv run python -m travel_data_platform.deployment.setup_github_env --stage $(STAGE) --dry-run

github-env-push:
	uv run python -m travel_data_platform.deployment.setup_github_env --stage $(STAGE)
