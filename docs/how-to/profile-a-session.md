---
icon: lucide/gauge
---

# How to profile a session

Find where a session spends its time, as a chart of its most costly calls.

## Prerequisites

The `profile` extra, which installs `pyinstrument` and `py-spy`:

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

The session records its calls from the moment it is made to the end of its
build: reading the configuration and importing the components, starting the
services, building and connecting the devices, then the presenters, the views
and the window. It writes an HTML file and logs its path:

```text
Profile written to .../profiles/MyApp/2026-10-01T09-30-00_4242.html
```

The file is in `profiles/<session>`, beside the session's `logs` folder, and
has the same name as the run's log file, so a profile and its log pair up.
The most recent runs are kept and older profiles are deleted.

Open it in a browser. The timeline view keeps calls in order, so the build
reads from left to right, and the widest blocks are where the time went.

## Profile the whole run

```python
MyApp(profile="run").run()
```

The profile ends when the session shuts down, so it also holds what the
session did while it was in use. Profiling slows the profiled thread a little,
and the times it shows by the same amount: compare parts of one profile, not
a profile with timings taken without one.

## Keep the profile somewhere else

```python
MyApp(profile="start", profile_dir="D:/profiles").run()
```

The file goes in that folder, under the same name, and nothing there is
deleted.

## What the profile does not show

`pyinstrument` samples the thread the session is made on. Device connections
and plans run on another thread, and show only as the time the main thread
waited for them. Services run in processes of their own and do not show at
all. Imports done before the session is made, when your module imports its
class, happen before the profile starts.

For every thread, and every service the session launches, run the session
under `py-spy`:

```bash
uv run py-spy record --subprocesses -o session.svg -- python my_session.py
```

`session.svg` is a flame graph of all of them. With `--format speedscope`,
`py-spy` writes a file for the speedscope viewer instead. On macOS, `py-spy`
needs `sudo`.

For imports, `python -X importtime my_session.py` prints the time each import
took to standard error, and a viewer such as `tuna` draws it.
