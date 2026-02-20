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
# Run a specific test file
pytest tests/test_config.py

# Run a specific test function
pytest tests/test_config.py::test_function_name

# Run tests matching a pattern
pytest -k "test_container"
```
