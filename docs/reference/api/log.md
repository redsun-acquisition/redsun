# Logging

`redsun` logs everything to the `redsun` logger. Usage is in
[Configure logging](../../how-to/configure-logging.md).

| Symbol | What it does |
| --- | --- |
| [`set_level`][redsun.log.set_level] | sets the level of the `redsun` logger |
| [`add_handler`][redsun.log.add_handler] | sends the logger's records to one more handler |
| [`remove_handler`][redsun.log.remove_handler] | stops sending records to a handler |
| [`Loggable`][redsun.log.Loggable] | gives a component a `logger` that names the component in each record |
| [`BufferHandler`][redsun.log.BufferHandler] | keeps the most recent records of the session in memory |
| [`log_buffer`][redsun.log.log_buffer] | returns the `BufferHandler` installed on the logger |
| [`SessionFileHandler`][redsun.log.SessionFileHandler] | writes the records of one run of a session to a rotated file |
| [`session_log`][redsun.log.session_log] | returns the `SessionFileHandler` installed on the logger, or on a service's, if any |
| [`service_of`][redsun.log.service_of] | names the service a record came from |

The built-in [`LogView`][redsun.view.qt.builtins.LogView] shows these records in
the application.

## Functions

::: redsun.log
    options:
      members:
        - set_level
        - add_handler
        - remove_handler
        - log_buffer
        - session_log
        - service_of

## Logging from a component

::: redsun.log.Loggable

## Session records

::: redsun.log.BufferHandler

::: redsun.log.SessionFileHandler
