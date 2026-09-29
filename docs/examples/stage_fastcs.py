"""The service of the guide "How to write a service with FastCS"."""

from __future__ import annotations

import asyncio
import os
import sys

from fastcs.attributes import AttrRW
from fastcs.control_system import FastCS
from fastcs.controllers import Controller
from fastcs.datatypes import Float
from fastcs.transports.epics.pva.transport import EpicsPVATransport
from p4p.client.asyncio import Context

READY = "stage ready"


# --8<-- [start:controller]
class Stage(Controller):
    def __init__(self) -> None:
        super().__init__()
        self.position = AttrRW(Float(units="mm"))


# --8<-- [end:controller]
# --8<-- [start:ready]
async def until_served(prefix: str, serving: asyncio.Future[None]) -> None:
    with Context("pva", conf={"EPICS_PVA_ADDR_LIST": "127.0.0.1"}) as client:
        while not serving.done():
            try:
                await asyncio.wait_for(client.get(f"{prefix}:PVI"), timeout=1.0)
            except TimeoutError:
                continue
            return
    serving.result()


# --8<-- [end:ready]
# --8<-- [start:serve]
async def serve(prefix: str) -> None:
    controller = Stage()
    controller.set_path([prefix])
    served = FastCS(controller, [EpicsPVATransport()])
    serving = asyncio.ensure_future(served.serve(interactive=False))
    await until_served(prefix, serving)
    print(READY, flush=True)
    if "REDSUN_SERVICE_NAME" in os.environ:
        await asyncio.to_thread(sys.stdin.read)
        serving.cancel()
    await asyncio.gather(serving, return_exceptions=True)


if __name__ == "__main__":
    prefix = os.environ.get("REDSUN_SERVICE_PREFIX", "STAGE:")
    asyncio.run(serve(prefix.rstrip(":")))
# --8<-- [end:serve]
