.PHONY: test lint ci

test:
	pytest api/tests/ -v --tb=short

lint:
	python -m ruff check api/app/ api/tests/

ci: lint test
