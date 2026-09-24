"""A p4p server standing in for a service that speaks PVAccess.

Run as ``python -m mock_pkg.service.pva_stand_in --pv SIM:VALUE --value 1``.
It serves one PV, prints its readiness line, and stops when its standard input
closes, the way a service written for redsun does.
"""

from __future__ import annotations

import argparse
import os
import sys
import threading

from p4p.nt import NTScalar
from p4p.server import Server
from p4p.server.thread import SharedPV

from mock_pkg.service.stand_in import stop_when_stdin_closes

READY = "pva stand-in ready"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pv", required=True, help="name of the PV served")
    parser.add_argument("--value", type=float, default=0.0)
    options = parser.parse_args()

    pv = SharedPV(nt=NTScalar("d"), initial=options.value)
    threading.Thread(target=stop_when_stdin_closes, daemon=True).start()
    with Server(providers=[{options.pv: pv}]):
        print(f"interface {os.environ.get('EPICS_PVAS_INTF_ADDR_LIST')}", flush=True)
        print(READY, flush=True)
        sys.stdin.read()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
