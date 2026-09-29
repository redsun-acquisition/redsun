---
icon: lucide/file-text
---

# Log files

Where a session writes its records, what a record looks like, and how long the
files are kept.
[How to configure logging](../how-to/configure-logging.md) sets the level and
adds destinations.

## Where they are

Under `logs` in the root of the session, which is `storage.base_dir` of the
session file, or the data folder of the user when it is not set:

| Platform | Root without `storage.base_dir` |
| --- | --- |
| Windows | `%LOCALAPPDATA%\redsun` |
| macOS | `~/Library/Application Support/redsun` |
| Linux | `~/.local/share/redsun` |

| File | Holds |
| --- | --- |
| `logs/<session>/app/<run>.log` | the records of the application, none of a service |
| `logs/<session>/services/<run>.<service>.log` | the records of one launched service |

`<session>` is the name of the session, `<run>` the time the run started and
the id of its process, such as `2026-09-13T14-02-46_8120`. A service's file is
created when the service first logs. When the root changes during a run,
through `set_base_dir` of the path provider, the files of the run move with it.

## How long they are kept

| What | Value |
| --- | --- |
| size at which a file rotates to `.log.1`, `.log.2`, ... | 10 MB |
| older files kept for each file | 5 |
| runs kept, counted when a run starts | 20 |

Starting a run deletes the application and service files of every run but the
19 most recent.

## What a record looks like

```text
[29-08-26|14:02:46][INFO][MyMotor -> stage]: Connected
[29-08-26|14:02:46][DEBUG][MyMotor -> stage]: setpoint=1.5 (motor.py:88)
```

A record starts with the date and time, as `day-month-year|hour:minute:second`,
and the level. What follows depends on what wrote it:

| Written by | Shape |
| --- | --- |
| a [`Loggable`][redsun.log.Loggable] declaring a `name` | `[Class -> name]` |
| a `Loggable` declaring none, or an empty one | `[Class]` |
| `logging.getLogger("redsun")` directly | nothing, just the message |

A record at any level but `INFO` ends with the file and line it came from, and
a record carrying a traceback is followed by it. A record a service printed
as JSON keeps the level and time of the service, and has no file and line.
