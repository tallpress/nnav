.PHONY: install run config-check test clean

install:
	uv sync

run:
	uv run nnav

config-check:
	uv run mypy src/nnav

test:
	uv run pytest tests/

clean:
	rm -rf .venv __pycache__ .mypy_cache .pytest_cache
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
