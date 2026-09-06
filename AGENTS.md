# Agent conventions

Rules for humans and coding agents working in this repository. The stack is
fixed; do not substitute tools.

## Stack (do not change)

- Python 3.12 with uv (`pyproject.toml`, no `requirements.txt`)
- DuckDB as the analytical store
- Parquet on disk; never CSV for raw or intermediate data
- dbt-duckdb for transformations
- pandas + pyarrow
- LightGBM + scikit-learn
- pytest
- ruff for lint and format
- pydantic for config validation
- GitHub Actions for CI

## Data and transforms

- Raw data is immutable. Writes go to `data/raw/` once and are not edited in
  place. Transformations belong in dbt (`dbt/models/`), not in Python.
- Python may ingest, run quality checks, assemble model matrices from marts,
  train, evaluate, and export. It must not reimplement warehouse logic.
- All timestamps are timezone-aware `Australia/Melbourne`. DST creates a
  duplicated hour in April and a missing hour in October; handle both
  explicitly and record the choice in `docs/decisions.md`.
- Never commit data files (Parquet or otherwise) or the `.duckdb` file.

## Honesty about sources and results

- Never fabricate API endpoints, dataset ids, column names, or numeric results.
- If something cannot be verified against a live source, mark it TODO and say
  so. Leave `verified: false` in `config/sources.yml` until confirmation.
- Open questions about data semantics go in `docs/decisions.md`, not a guess
  in code, YAML, or the data dictionary.

## Modelling

- Baselines are mandatory before any ML model. Report MASE against a seasonal
  naive forecast (hourly seasonality, confirmed once the grain is verified).
- Time series validation is rolling-origin only. Never use a random split.

## Code layout

- Notebooks are exploration only. Reused code moves into `src/melbourne_footfall/`
  or a dbt model.
- Package layout: `ingest`, `quality`, `features`, `models`, `export`.
- Config is validated by `melbourne_footfall.config.load_sources_config`.

## Commands

Use the Makefile: `setup`, `ingest`, `build`, `features`, `train`, `evaluate`,
`export`, `test`, `lint`, `clean`. Targets that are not implemented yet must
echo a not-implemented message and exit 0.
