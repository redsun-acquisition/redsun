"""The service of the guide "How to write a service with FastCS"."""

from __future__ import annotations

import asyncio

from fastcs.attributes import AttrRW
from fastcs.control_system import FastCS
from fastcs.controllers import Controller
from fastcs.datatypes import Float
from fastcs.transports.epics.pva.transport import EpicsPVATransport

from redsun.services import (
    configure_logging,
    identity,
    ready_when_reachable,
    wait_for_stop,
)


# --8<-- [start:controller]
class Stage(Controller):
    def __init__(self) -> None:
        super().__init__()
        self.position = AttrRW(Float(units="mm"))


# --8<-- [end:controller]
# --8<-- [start:serve]
async def serve(prefix: str) -> None:
    controller = Stage()
    controller.set_path([prefix])
    served = FastCS(controller, [EpicsPVATransport()])
    serving = asyncio.ensure_future(served.serve(interactive=False))
    announcing = asyncio.ensure_future(ready_when_reachable(f"{prefix}:PVI"))
    stopping = asyncio.ensure_future(wait_for_stop())
    await asyncio.wait({serving, stopping}, return_when=asyncio.FIRST_COMPLETED)
    for task in (serving, announcing, stopping):
        task.cancel()
    await asyncio.gather(serving, announcing, stopping, return_exceptions=True)
    if not serving.cancelled():
        serving.result()


if __name__ == "__main__":
    configure_logging()
    me = identity()
    prefix = me.prefix if me else "STAGE:"
    asyncio.run(serve(prefix.rstrip(":")))
# --8<-- [end:serve]
