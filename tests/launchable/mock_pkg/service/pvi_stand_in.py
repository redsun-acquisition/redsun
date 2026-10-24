"""A p4p server standing in for a service that describes its device with PVI.

Run as `python -m mock_pkg.service.pvi_stand_in` by a session, which gives it
its prefix. The root's PVI lists one sub-device, `xy`, holding one signal, `x`,
so a device reading that structure has its children only once it connects.
"""

from __future__ import annotations

import asyncio

from p4p import Type, Value
from p4p.nt import NTScalar
from p4p.server import Server
from p4p.server.thread import SharedPV

from redsun.services import identity, ready_when_reachable, wait_for_stop


def structure(entries: dict[str, dict[str, str]]) -> SharedPV:
    """Return a PV serving a PVI structure that lists *entries*."""
    fields = [
        (name, ("S", None, [(kind, "s") for kind in entry]))
        for name, entry in entries.items()
    ]
    shape = Type([("value", ("S", None, fields))])
    return SharedPV(initial=Value(shape, {"value": entries}))


async def serve(prefix: str) -> None:
    pvs = {
        f"{prefix}PVI": structure({"xy": {"d": f"{prefix}XY:PVI"}}),
        f"{prefix}XY:PVI": structure({"x": {"rw": f"{prefix}XY:X"}}),
        f"{prefix}XY:X": SharedPV(nt=NTScalar("d"), initial=0.0),
    }
    announcing = asyncio.ensure_future(ready_when_reachable(f"{prefix}PVI"))
    with Server(providers=[pvs]):
        await announcing
        await wait_for_stop()


def main() -> int:
    service = identity()
    asyncio.run(serve(service.prefix if service is not None else "PVI:"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
