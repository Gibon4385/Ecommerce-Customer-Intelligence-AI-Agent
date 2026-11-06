#!/usr/bin/env bash
set -euo pipefail
export UV_CACHE_DIR="${UV_CACHE_DIR:-$PWD/.uv-cache}"
unset VIRTUAL_ENV

uv run ruff check .
uv run mypy src scripts evals
uv run python scripts/bootstrap_demo_raw.py
uv run python scripts/build_ops_marts.py
uv run python scripts/generate_synthetic_ops.py
uv run python scripts/validate_data.py
uv run pytest tests/deterministic \
  --junitxml=reports/verification/pytest-junit.xml \
  --cov=src/ecommerce_agent \
  --cov-report=term-missing \
  --cov-report=json:reports/verification/coverage.json
uv run python -m scripts.run_portfolio_demos > reports/verification/demo_flows.json
uv run python -m scripts.verify_clean_runtime
uv run python -m scripts.write_verification_summary

