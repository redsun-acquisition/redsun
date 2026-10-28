"""The service of the guide "How to serve a FastCS controller over sharedbox"."""

from __future__ import annotations

import asyncio

from fastcs.attributes import AttrR, AttrRW
from fastcs.controllers import Controller
from fastcs.datatypes import Float, String
from fastcs.methods import command

from redsun.services import configure_logging, identity, serve_controller
from redsun.services.sharedbox import BoxTransport


# --8<-- [start:controller]
class MyController(Controller):
    def __init__(self) -> None:
        super().__init__()
        self.exposure = AttrRW(Float(units="ms", min=0.0))
        self.state = AttrR(String(length=16), initial_value="idle")

    @command()
    async def start(self) -> None:
        await self.state.update("running")


# --8<-- [end:controller]
# --8<-- [start:serve]
if __name__ == "__main__":
    configure_logging()
    prefix = None if identity() else "MYAPP:DET"
    try:
        asyncio.run(serve_controller(MyController(), BoxTransport(), prefix))
    except KeyboardInterrupt:
        pass
# --8<-- [end:serve]
