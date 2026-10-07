---
icon: lucide/gauge
---

# How to profile a session

This guide shows where a session spends its time, as a chart of its slowest
calls.

## Prerequisites

You need the `profile` extra, which installs `pyinstrument` and `py-spy`:

=== "uv"

    ```bash
    uv add "redsun[profile]"
    ```

=== "pip"

    ```bash
    pip install "redsun[profile]"
    ```

## Profile the start

```python
MyApp(profile="start").run()
```

The session records its calls from the moment you make it to the end of its
build. That covers reading the configuration and importing the components,
starting the services, building and connecting the devices, and then building
the presenters, the views and the window. It writes an HTML file and logs the
path:

```text
Profile written to .../profiles/MyApp/2026-10-01T09-30-00_4242.html
```

The file is in `profiles/<session>`, beside the session's `logs` folder, and
has the same name as the run's log file, so a profile and its log pair up. The
session keeps the most recent runs and deletes older profiles.

Open the file in a browser. The timeline view keeps calls in order, so the
build reads from left to right, and the widest blocks are where the time went.

## Profile the whole run

```python
MyApp(profile="run").run()
```

The profile ends when the session shuts down, so it also holds what the
session did while you used it.

!!! warning "Profiled times are slower than real ones"

    Profiling slows the profiled thread a little, and the times it shows are
    slower by the same amount. Compare parts of one profile with each other, not
    a profile with timings taken without one.

## Keep the profile somewhere else

```python
MyApp(profile="start", profile_dir="D:/profiles").run()
```

The file goes in that folder under the same name, and the session deletes
nothing there.

## What the profile does not show

`pyinstrument` samples the thread the session is made on. Device connections
and plans run on another thread, so they show only as the time the main thread
waited for them. Services run in processes of their own, so they don't show at
all. Imports that happen before the session is made, when your module imports
its class, come before the profile starts.

To see every thread and every service the session launches, run the session
under `py-spy`:

```bash
uv run py-spy record --subprocesses -o session.svg -- python my_session.py
```

`session.svg` is a flame graph of all of them. With `--format speedscope`,
`py-spy` writes a file for the speedscope viewer instead. On macOS, `py-spy`
needs `sudo`.

To time imports, run `python -X importtime my_session.py`, which prints the
time each import took to standard error. A viewer such as `tuna` can draw it.
