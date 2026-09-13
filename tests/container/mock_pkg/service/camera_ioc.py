"""A caproto IOC serving one camera setting, stopped when its standard input closes.

Run as ``python -m mock_pkg.service.camera_ioc --prefix CAM:``.
"""

from __future__ import annotations

import signal
import sys
import threading

from caproto.server import PVGroup, ioc_arg_parser, pvproperty, run


def stop_when_stdin_closes() -> None:
    sys.stdin.read()
    signal.raise_signal(signal.SIGINT)


class Camera(PVGroup):  # type: ignore[misc]
    exposure = pvproperty(value=0.25, name="Exposure")


if __name__ == "__main__":
    options, run_options = ioc_arg_parser(default_prefix="CAM:", desc="stand-in camera")
    threading.Thread(target=stop_when_stdin_closes, daemon=True).start()
    run(Camera(**options).pvdb, **{**run_options, "interfaces": ["127.0.0.1"]})
