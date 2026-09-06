.PHONY: setup ingest build features train evaluate export test lint clean

setup:
	uv sync
	uv run python -c "from pathlib import Path; src, dst = Path('dbt/profiles.yml.example'), Path('dbt/profiles.yml'); dst.write_text(src.read_text(encoding='utf-8'), encoding='utf-8') if not dst.exists() else None"

ingest:
	@echo not implemented: ingest

build:
	@echo not implemented: build

features:
	@echo not implemented: features

train:
	@echo not implemented: train

evaluate:
	@echo not implemented: evaluate

export:
	@echo not implemented: export

test:
	uv run pytest

lint:
	uv run ruff check .
	uv run ruff format --check .

clean:
	uv run python -c "import shutil; from pathlib import Path; targets = ['.pytest_cache', '.ruff_cache', 'dbt/target', 'dbt/logs', 'dbt/dbt_packages']; [shutil.rmtree(t, ignore_errors=True) for t in targets]; [shutil.rmtree(p, ignore_errors=True) for p in Path('.').rglob('__pycache__') if '.venv' not in p.parts]"
