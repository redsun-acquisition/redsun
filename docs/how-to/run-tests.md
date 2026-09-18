# Run tests

Run the `redsun` test suite, type-check it against both Qt bindings, and
produce coverage reports.

## Prerequisites

[Install `redsun` with development dependencies](installation.md#install-development-dependencies).

## Run everything

`tox` runs the environments CI runs, each built from `uv.lock`:

```bash
uv run tox
```

That lints, type-checks against both Qt bindings, runs the tests and builds
the docs. Run one environment with `-e`:

```bash
uv run tox -e tests
uv run tox -e mypy-pyqt
```

| environment | what it runs |
| --- | --- |
| `lint` | `ruff check --fix` then `ruff format` |
| `mypy-pyqt` / `mypy-pyside` | `mypy` against that Qt binding |
| `tests` | `pytest -q` |
| `docs` | `zensical build` then the cross-reference check |

## Run specific tests

Arguments after `--` go to `pytest`:

```bash
# SDK tests only
uv run tox -e tests -- tests/sdk/

# a specific test function
uv run tox -e tests -- tests/container/test_container.py::test_function_name

# everything matching a pattern
uv run tox -e tests -- -k "test_wiring"
```

The project environment skips the sync, so it is faster while editing:

```bash
uv run pytest tests/sdk/ -x
```

Tests marked `@pytest.mark.qt` are skipped when no display is available.

## Run the tests against a service outside the process

Tests marked `@pytest.mark.compose` talk to an IOC in a container started from
`tests/compose/compose.yaml`. They are skipped unless `REDSUN_COMPOSE` is set,
so the rest of the suite needs no container runtime. With Docker running:

```bash
docker compose -f tests/compose/compose.yaml up --detach --wait
REDSUN_COMPOSE=1 uv run pytest -m compose
docker compose -f tests/compose/compose.yaml down
```

The IOC listens on `127.0.0.1` port 5064, the default Channel Access port, so
stop any other IOC on that port first. CI runs these tests in their own job on
Ubuntu.

## Type-check against both Qt bindings

`mypy` checks the tests in strict mode along with the sources. `redsun`
supports `pyqt6` and `pyside6`, whose type stubs disagree on some signatures,
so both are checked:

```bash
uv run tox -e mypy-pyqt,mypy-pyside
```

Each environment installs only its own binding and sets `QT_API`, which
selects the branches `qtpy` shows the type checker. A green `mypy-pyqt` says
nothing about `mypy-pyside`.

Running `mypy` in the project environment is not the same check: that
environment holds both bindings, so it reports errors neither binding has on
its own and can miss errors CI catches.

## Generate a coverage report

`pyproject.toml` configures the coverage sources:

```bash
uv run pytest --cov --cov-report=html
```

Open `htmlcov/index.html` in a browser.
