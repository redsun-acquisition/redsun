"""The service launched in the "Putting a device behind a service" tutorial."""

from __future__ import annotations

# --8<-- [start:imports]
import os
import signal
import sys
import threading

from caproto.server import PVGroup, ioc_arg_parser, pvproperty, run

# --8<-- [end:imports]


# --8<-- [start:stage]
class Stage(PVGroup):
    position = pvproperty(value=0.0, name="Position")


# --8<-- [end:stage]
# --8<-- [start:stop]
def stop_when_stdin_closes() -> None:
    sys.stdin.read()
    signal.raise_signal(signal.SIGINT)


# --8<-- [end:stop]
# --8<-- [start:main]
if __name__ == "__main__":
    prefix = os.environ.get("REDSUN_SERVICE_PREFIX", "STAGE:")
    options, run_options = ioc_arg_parser(default_prefix=prefix, desc="stage")
    if "REDSUN_SERVICE_NAME" in os.environ:
        threading.Thread(target=stop_when_stdin_closes, daemon=True).start()
    run(Stage(**options).pvdb, **{**run_options, "interfaces": ["127.0.0.1"]})
# --8<-- [end:main]
