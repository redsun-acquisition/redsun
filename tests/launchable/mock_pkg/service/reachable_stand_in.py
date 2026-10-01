"""A p4p server that prints no line of its own once it serves.

Run as `python -m mock_pkg.service.reachable_stand_in --pv REACH:VALUE`. It
counts as ready once `ready_when_reachable` reaches its PV, and stops when the
session asks. With `--late`, it starts serving only after a few seconds, as a
slow server does.
"""

from __future__ import annotations

import argparse
import asyncio

from p4p.nt import NTScalar
from p4p.server import Server
from p4p.server.thread import SharedPV

from redsun.services import ready_when_reachable, wait_for_stop

LATE_START = 2.5
"""Seconds a late stand-in waits before it serves."""


async def serve(name: str, late: bool) -> None:
    pv = SharedPV(nt=NTScalar("d"), initial=0.0)
    announcing = asyncio.ensure_future(ready_when_reachable(name))
    if late:
        await asyncio.sleep(LATE_START)
    with Server(providers=[{name: pv}]):
        await announcing
        await wait_for_stop()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pv", required=True, help="name of the PV served")
    parser.add_argument("--late", action="store_true", help="serve after a delay")
    options = parser.parse_args()
    asyncio.run(serve(options.pv, options.late))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
