"""A service serving the test controller as sharedbox boxes.

Run as `python -m mock_pkg.service.box_stand_in` by a session, which gives it
its prefix and its ready text.
"""

from __future__ import annotations

import asyncio

from mock_pkg.box_controller import BoxController
from redsun.services import serve_controller
from redsun.services.sharedbox import BoxTransport


def main() -> int:
    asyncio.run(serve_controller(BoxController(), BoxTransport()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
