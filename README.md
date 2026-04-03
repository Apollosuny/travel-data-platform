# travel-data-platform

Python worker and ingestion pipeline for flight price tracking.

Current scope:

- load active flight watches from Postgres
- fetch flight offers from Google Flights
- normalize and persist ingestion results
- support scheduled batch execution
- provide a foundation for future data engineering expansion

## Tech stack

- Python 3.12
- uv
- Playwright
- PostgreSQL
- SQLAlchemy
- Alembic
- Pydantic
- pytest
- Ruff
- mypy

---

## Project structure

```txt
alembic/
debug/
src/
  travel_data_platform/
    config.py
    exceptions.py
    logging.py

    database/
      base.py
      session.py
      models/
        fetch_run.py
        raw_flight_offer.py
        normalized_flight_offer.py
        flight_watch.py

    domain/
      flight.py
      ingestion.py

    providers/
      base.py
      google_flights/
        client.py
        parser.py
        schemas.py
        debug/
          artifacts.py
        fetchers/
          base.py
          browser_fetcher.py
        runtime/
          browser_runtime.py

    repositories/
      fetch_run_repository.py
      raw_flight_offer_repository.py
      normalized_flight_offer_repository.py
      flight_watch_repository.py

    services/
      ingestion_service.py
      batch_ingestion_service.py
      flight_watch_service.py
      watch_query_service.py

    workers/
      batch_fetch_prices.py
      seed_flight_watches.py
      test_db.py

tests/
  unit/
  integration/
```

---

## Database design

This project uses a shared PostgreSQL database with separate schemas.

### `ingestion`

Owned by the Python worker.

Main tables:

- `ingestion.fetch_runs`
- `ingestion.raw_flight_offers`
- `ingestion.normalized_flight_offers`

### `app`

Used for application-facing business data.

Current table:

- `app.flight_watches`

This separation allows:

- Spring Boot to own business tables in `app`
- Python to own ingestion tables in `ingestion`
- future analytics expansion without mixing responsibilities

---

## Environment variables

Create a `.env` file from `.env.example`.

Example:

```env
APP_ENV=development
LOG_LEVEL=INFO
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/travel_platform
```

---

## Setup

### 1. Install dependencies

```bash
uv sync --dev
```

### 2. Install Playwright browser

```bash
uv run playwright install chromium
```

### 3. Apply database migrations

```bash
uv run alembic upgrade head
```

### 4. Seed sample flight watches

```bash
uv run python -m travel_data_platform.workers.seed_flight_watches
```

---

## Common commands

### Run all tests

```bash
uv run pytest -v
```

### Lint

```bash
uv run ruff check src tests
```

### Format

```bash
uv run ruff format src tests
```

### Type check

```bash
uv run mypy src
```

### Run batch worker

```bash
uv run python -m travel_data_platform.workers.batch_fetch_prices
```

### Create a new migration

```bash
uv run alembic revision --autogenerate -m "your migration message"
```

### Apply latest migration

```bash
uv run alembic upgrade head
```

---

## Makefile shortcuts

If using the provided `Makefile`:

```bash
make install
make lint
make format
make typecheck
make test
make check
make upgrade
make migrate m="your migration message"
```

---

## Current ingestion flow

The batch worker runs this flow:

1. load due active watches from `app.flight_watches`
2. build `FlightQuery` objects
3. open a shared browser for the batch
4. fetch flight results from Google Flights
5. write debug artifacts locally
6. persist run metadata into `ingestion.fetch_runs`
7. persist raw offers into `ingestion.raw_flight_offers`
8. persist normalized offers into `ingestion.normalized_flight_offers`
9. update `last_checked_at` on successful watches
10. log batch summary and exit

---

## Debug artifacts

During development, the worker writes debug artifacts into:

```txt
debug/google_flights/
```

Typical files include:

- raw HTML
- body text
- extracted offers JSON
- batch summary JSON

These files are for local debugging and should not be treated as durable storage.

---

## Operational behavior

The worker is designed to be cron-ready.

Key properties:

- batch execution
- shared browser across a batch
- per-watch error isolation
- database persistence for runs and offers
- summary logging
- non-zero exit code when failures occur

This makes it suitable for future scheduled deployment.

---

## Intended architecture

### Python worker

Responsible for:

- batch ingestion
- crawling and normalization
- writing to `ingestion.*`

### Spring Boot backend

Responsible for:

- business APIs
- CRUD for `app.flight_watches`
- airport reference data
- reading from `ingestion.*`
- alert and app-facing query logic

### Future direction

This repository is intended to evolve into a more complete data engineering project, including:

- richer ingestion pipelines
- reference data management
- data quality checks
- scheduling and orchestration
- analytics-friendly models

---

## Notes

- Google Flights extraction is subject to upstream page changes.
- Browser-based crawling is more resource-intensive than standard HTTP ingestion.
- The current worker is intended for scheduled execution, not user-facing live request handling.
- Postgres schemas are intentionally separated for cleaner ownership boundaries.

---

## Status

Current status:

- batch worker is working
- DB persistence is working
- flight watches are loaded from DB
- shared browser batch execution is working

Recommended next steps:

- add airport reference data
- build Spring Boot backend
- add alerts and app-facing read models
- prepare deployment for scheduled execution
