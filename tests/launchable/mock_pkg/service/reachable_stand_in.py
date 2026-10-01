"""A p4p server that prints no line of its own once it serves.

Run as `python -m mock_pkg.service.reachable_stand_in --pv REACH:VALUE`. It
counts as ready once `ready_when_reachable` reaches its PV, and stops when the
session asks.
"""

from __future__ import annotations

import argparse
import asyncio

from p4p.nt import NTScalar
from p4p.server import Server
from p4p.server.thread import SharedPV

from redsun.services import ready_when_reachable, wait_for_stop


async def serve(name: str) -> None:
    pv = SharedPV(nt=NTScalar("d"), initial=0.0)
    with Server(providers=[{name: pv}]):
        await ready_when_reachable(name)
        await wait_for_stop()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pv", required=True, help="name of the PV served")
    options = parser.parse_args()
    asyncio.run(serve(options.pv))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
