# Run tests

This guide covers how to run the `redsun` test suite and generate coverage reports.

## Prerequisites

Make sure you have [installed `redsun` with development dependencies](installation.md#install-development-dependencies).

## Run all tests

Run the tests from the project root:

```bash
uv run pytest
```

Qt-dependent tests are marked with `@pytest.mark.qt` and are skipped
automatically when no display environment is available.

## Generate coverage report

Coverage sources are configured in `pyproject.toml`, so no extra flags are
needed:

```bash
uv run pytest --cov --cov-report=html
```

This generates an `htmlcov/` directory. Open `htmlcov/index.html` in your browser to view it.

## Run specific tests

```bash
# Run SDK tests only
uv run pytest tests/sdk/

# Run container tests only
uv run pytest tests/container/

# Run a specific test function
uv run pytest tests/container/test_container.py::test_function_name

# Run tests matching a pattern
uv run pytest -k "test_storage"
```

## Type-check the test suite

Tests are covered by mypy strict mode alongside the sources. Run the
configuration-driven form (the Qt binding shim pins what CI checks):

```bash
uv run mypy --ignore-missing-imports $(uv run qtpy mypy-args)
```
