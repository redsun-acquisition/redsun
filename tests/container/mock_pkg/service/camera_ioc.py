"""A caproto IOC serving one camera setting, stopped when its standard input closes.

Run as ``python -m mock_pkg.service.camera_ioc --prefix CAM:``.
"""

from __future__ import annotations

import threading

from caproto.server import PVGroup, ioc_arg_parser, pvproperty, run
from mock_pkg.service.stand_in import stop_when_stdin_closes


class Camera(PVGroup):  # type: ignore[misc]
    exposure = pvproperty(value=0.25, name="Exposure")


if __name__ == "__main__":
    options, run_options = ioc_arg_parser(default_prefix="CAM:", desc="stand-in camera")
    threading.Thread(target=stop_when_stdin_closes, daemon=True).start()
    run(Camera(**options).pvdb, **{**run_options, "interfaces": ["127.0.0.1"]})
