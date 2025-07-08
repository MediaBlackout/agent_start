.PHONY: dev test

dev:
	pip install -e .[dev]
	pre-commit install

test:
	pytest
