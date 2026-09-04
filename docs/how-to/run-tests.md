# Run tests

This guide covers how to run the `redsun` test suite, check its types against
both Qt bindings, and generate coverage reports.

## Prerequisites

Make sure you have [installed `redsun` with development dependencies](installation.md#install-development-dependencies).

## Run everything

`tox` runs the same environments CI does, each built from `uv.lock`:

```bash
uv run tox
```

That covers linting, both Qt type-checking legs, the test suite and the
documentation build. Run one environment on its own with `-e`:

```bash
uv run tox -e tests
uv run tox -e mypy-pyqt
```

| environment | what it runs |
| --- | --- |
| `lint` | `ruff check --fix` then `ruff format` |
| `mypy-pyqt` / `mypy-pyside` | mypy against that Qt binding |
| `tests` | `pytest -q` |
| `docs` | `zensical build` then the cross-reference guard |

## Run specific tests

Arguments after `--` reach pytest:

```bash
# SDK tests only
uv run tox -e tests -- tests/sdk/

# a specific test function
uv run tox -e tests -- tests/container/test_container.py::test_function_name

# everything matching a pattern
uv run tox -e tests -- -k "test_storage"
```

For a fast edit-and-run loop the project environment is quicker, since it skips
the sync:

```bash
uv run pytest tests/sdk/ -x
```

Qt-dependent tests are marked with `@pytest.mark.qt` and are skipped
automatically when no display environment is available.

## Type-check against both Qt bindings

Tests are covered by mypy strict mode alongside the sources. `redsun` supports
PyQt6 and PySide6, whose type stubs disagree about some signatures, so both are
checked:

```bash
uv run tox -e mypy-pyqt,mypy-pyside
```

Each environment installs only its own binding and sets `QT_API`, which is what
decides the branches `qtpy` exposes to the type checker. A green `mypy-pyqt`
says nothing about `mypy-pyside`.

Running `mypy` against the project environment instead is not equivalent: that
environment holds both bindings at once, so it reports errors neither binding
produces on its own and can miss errors CI catches.

## Generate a coverage report

Coverage sources are configured in `pyproject.toml`, so no extra flags are
needed:

```bash
uv run pytest --cov --cov-report=html
```

This generates an `htmlcov/` directory. Open `htmlcov/index.html` in your
browser to view it.
