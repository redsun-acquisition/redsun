# Run tests

This guide covers how to run the `redsun` test suite and generate coverage reports.

## Prerequisites

Make sure you have [installed `redsun` with development dependencies](installation.md#install-development-dependencies).

## Run all tests

Run the tests from the project root:

```bash
pytest
```

## Generate coverage report

Obtain a test coverage report:

```bash
pytest --cov=redsun --cov-report=html
```

This generates an `htmlcov/` directory. Open `htmlcov/index.html` in your browser to view it.

## Run specific tests

```bash
# Run SDK tests only
pytest tests/sdk/

# Run container tests only
pytest tests/container/

# Run a specific test function
pytest tests/container/test_container.py::test_function_name

# Run tests matching a pattern
pytest -k "test_storage"
```
