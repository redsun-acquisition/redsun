"""The service launched in the "Putting a device behind a service" tutorial."""

from __future__ import annotations

# --8<-- [start:imports]
from caproto.server import PVGroup, ioc_arg_parser, pvproperty, run

from redsun.services import identity, stop_on_request

# --8<-- [end:imports]


# --8<-- [start:stage]
class Stage(PVGroup):
    position = pvproperty(value=0.0, name="Position")


# --8<-- [end:stage]
# --8<-- [start:main]
if __name__ == "__main__":
    me = identity()
    prefix = me.prefix if me else "STAGE:"
    options, run_options = ioc_arg_parser(default_prefix=prefix, desc="stage")
    stop_on_request()
    run(Stage(**options).pvdb, **{**run_options, "interfaces": ["127.0.0.1"]})
# --8<-- [end:main]
