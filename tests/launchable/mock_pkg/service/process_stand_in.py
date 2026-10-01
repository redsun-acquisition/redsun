"""A service built on the functions `redsun.services` gives a service process.

Run as `python -m mock_pkg.service.process_stand_in`. It prints what the
session told it, prints the declared ready text, and exits 0 once asked to
stop: by awaiting the request, or with `--blocking` through `SIGINT`, as a
blocking server does.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time

from redsun.services import identity, ready, stop_on_request, wait_for_stop


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--blocking", action="store_true")
    options = parser.parse_args()

    print(f"identity {identity()}", flush=True)
    if options.blocking:
        stop_on_request()
        ready()
        try:
            while True:
                time.sleep(0.05)
        except KeyboardInterrupt:
            pass
    else:
        ready()
        asyncio.run(wait_for_stop())
    print("asked to stop", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
