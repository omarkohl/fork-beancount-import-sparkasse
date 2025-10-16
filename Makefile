.PHONY: \
	check-format \
	lint \
	check-type \
	check-code-quality \
    tests

check-format:
	uv run python --version
	uv run which python
	uv run python --version
	uv run black --check beancount_import_sparkasse
	uv run isort --check-only beancount_import_sparkasse

lint:
	uv run flake8 beancount_import_sparkasse

check-type:

check-code-quality: check-format lint check-type

tests:
	uv run python --version
	uv run which python
	uv run python --version
	uv run pytest tests
