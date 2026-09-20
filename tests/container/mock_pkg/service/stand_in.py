"""A service standing in for a real one, its behaviour chosen on the command line.

Run as ``python -m mock_pkg.service.stand_in``. By default it prints its
readiness line and runs until its standard input closes, then cleans up and
exits 0, the way a service written for redsun does.
"""

from __future__ import annotations

import argparse
import os
import signal
import sys
import threading
import time
from pathlib import Path

READY = "stand-in ready"


def stop_when_stdin_closes() -> None:
    sys.stdin.read()
    signal.raise_signal(signal.SIGINT)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-ready", action="store_true", help="never print READY")
    parser.add_argument("--ignore-stdin", action="store_true")
    parser.add_argument("--ignore-sigint", action="store_true")
    parser.add_argument("--exit", type=int, help="exit with this code once ready")
    parser.add_argument("--marker", type=Path, help="file written on clean exit")
    parser.add_argument("--say", help="a line printed once ready")
    options = parser.parse_args()

    if options.ignore_sigint:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
    if not options.ignore_stdin:
        threading.Thread(target=stop_when_stdin_closes, daemon=True).start()

    print(f"port {os.environ.get('EPICS_CA_SERVER_PORT')}", flush=True)
    print(
        f"service {os.environ.get('REDSUN_SERVICE_NAME')} "
        f"prefix {os.environ.get('REDSUN_SERVICE_PREFIX')}",
        flush=True,
    )
    if not options.no_ready:
        print(READY, flush=True)
    if options.say is not None:
        print(options.say, flush=True)
    if options.exit is not None:
        print("exiting on request", flush=True)
        return int(options.exit)
    try:
        while True:
            time.sleep(0.05)
    except KeyboardInterrupt:
        # before printing: with the launcher gone, nothing reads the output
        if options.marker is not None:
            options.marker.write_text("cleaned up")
        print("cleaned up", flush=True)
        return 0


if __name__ == "__main__":
    sys.exit(main())
