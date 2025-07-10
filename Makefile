.PHONY: dev fmt lint test

dev:
	pip install -e .[dev]
	pre-commit install




fmt:
	ruff format src tests
	isort src tests
	black src tests

lint:
	ruff check .

test:
	pytest
