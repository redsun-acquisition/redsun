---
icon: lucide/flask-conical
---

# How to test a plugin

Test the components and services of a plugin with the fixtures `redsun` uses
for its own tests, from [`redsun.testing`](../reference/api/testing.md).

## Prerequisites

A plugin package with `pytest` tests. See
[Package components as a plugin](package-a-plugin.md). The blocks below are
parts of one test module; the whole module is at the end.

## Install the fixtures

Add `redsun` with the `testing` extra to the plugin's development
dependencies:

```bash
uv add --dev "redsun[testing]"
```

## Load them

Load the module as a `pytest` plugin, in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
addopts = "-p redsun.testing"
```

From then on every test writes session log files, acquisition files and
catalogs under its own `tmp_path` instead of the user's directories, and
drops the `psygnal` emissions it left queued for another thread. Nothing
loads the module unless a suite asks for it, so these fixtures never reach a
project that only installs `redsun`.

The module defines no `qapp` fixture. A session with a window needs a
`QApplication`: take the `qapp` fixture of `pytest-qt`, or define one.

## Build a session

Ask for [`build`][redsun.testing.build]. It builds a session class with the
configuration given, and shuts the session down when the test ends:

```{.python}
--8<-- "docs/examples/plugin_tests.py:build"
```

`mock: True` connects every device to a simulated backend, as in
[Run without hardware](run-without-hardware.md). It does not suit a device
whose signals come from its service when it connects, as a `fastcs` device's
do: mocked, it has none. Test such a device against its service instead.

## Start a service

Declare the service once, with the [`Launch`][redsun.Launch] a session class
uses:

```{.python}
--8<-- "docs/examples/plugin_tests.py:declare"
```

Ask for [`start_service`][redsun.testing.start_service] and give it the name
the service is declared under, the `Launch`, and the transport the session
file names under `services.transport`:

```{.python}
--8<-- "docs/examples/plugin_tests.py:service"
```

The service is stopped when the test ends, and the EPICS address list it
added itself to is restored, so the next test starts from the same list. The
test reads the prefix from the service it gets back.

## The example in full

??? example "The whole module"

    ```{.python}
    --8<-- "docs/examples/plugin_tests.py"
    ```
