# GitHub Actions setup

The workflows read their configuration from the **`prod` GitHub Environment**:

| Workflow | Trigger | Uses |
|---|---|---|
| `batch-fetch-prices.yml` | manual (schedule is commented out) | `secrets.DATABASE_URL`, `vars.LOG_LEVEL`, `vars.APP_ENV` |
| `db-migrate.yml` | manual only | `secrets.DATABASE_URL`, `vars.APP_ENV` |

The keys are declared once in [`github-envs.toml`](./github-envs.toml). Their values live in
`docs/deployment/.env.github.<stage>`, which is gitignored, and are pushed with the `gh` CLI.

## Prerequisites

- `gh` CLI, logged in with an account that has **admin** access to the repository.
  The script checks this and stops before changing anything if access is missing.
  ```bash
  gh auth status
  gh auth switch --user <repo-owner>   # if another account is active
  ```
- A Neon project. Use the **direct** connection string, not the `-pooler` host, and change the
  scheme to the psycopg driver:
  ```
  postgresql+psycopg://<user>:<password>@ep-xxx.<region>.aws.neon.tech/neondb?sslmode=require
  ```

## 1. Push secrets and variables

```bash
make github-env-init STAGE=prod      # creates docs/deployment/.env.github.prod
# edit docs/deployment/.env.github.prod and fill in DATABASE_URL (LOG_LEVEL / APP_ENV are optional)
make github-env-dry-run STAGE=prod   # preview, and validate the value formats
make github-env-push STAGE=prod      # create the environment (branch: main) and push
```

- Re-run `github-env-init` after adding a key to `github-envs.toml`. It only appends the new keys.
- Secrets that already exist on GitHub are overwritten only if you confirm each one.
- If a value does not match its `pattern` (for example a `postgresql://` URL without `+psycopg`),
  the push is rejected before anything is sent.

## 2. Initialise or upgrade the database

Run **Actions → db-migrate → Run workflow** on `main`. This workflow:

1. creates the `ingestion` and `app` schemas if they are missing (needed for a fresh Neon database),
2. runs `alembic upgrade head`.

Run it before merging any PR that adds a migration. The worker selects the new columns,
so it fails against a database that has not been migrated.

## 3. Add a watch and run the batch

```sql
INSERT INTO app.flight_watches
  (id, origin, destination, departure_date, return_date, adults, target_price,
   is_active, check_frequency_minutes, departure_time_from, departure_time_to, max_stops)
VALUES
  (gen_random_uuid(), 'KUL', 'HAN', '2026-11-24', NULL, 1, 2200000,
   true, 360, '18:00', '18:30', 0);
```

1. Run **Actions → batch-fetch-prices → Run workflow** with `log_level=DEBUG`.
2. In the log, check that `watch_cheapest_offer` shows `currency=VND` and the expected departure time.
3. To run automatically, uncomment the `schedule` block in `batch-fetch-prices.yml`.
