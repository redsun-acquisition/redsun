"""A service serving the test controller over PVAccess.

Run as `python -m mock_pkg.service.pva_controller_stand_in` by a session, which
gives it its prefix and its ready text.
"""

from __future__ import annotations

import asyncio

from fastcs.transports.epics.pva.transport import EpicsPVATransport

from mock_pkg.box_controller import BoxController
from redsun.services import serve_controller


def main() -> int:
    asyncio.run(serve_controller(BoxController(), EpicsPVATransport()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
