"""A service built on the functions `redsun.services` gives a service process.

Run as `python -m mock_pkg.service.process_stand_in`. It logs its level and
one line at `DEBUG` through `logging` and `loguru`, and one through the
`redsun` logger tree. It prints what the session told it, prints the declared
ready text, and exits 0 once asked to stop: by awaiting the request, or with
`--blocking` through `SIGINT`, as a blocking server does. `--select` blocks in
a system call that only a signal ends, as a server waiting for a client does;
it needs a POSIX `select` on a pipe.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import select
import sys
import time

from loguru import logger as loguru_logger

from redsun.services import (
    configure_logging,
    identity,
    ready,
    stop_on_request,
    wait_for_stop,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--blocking", action="store_true")
    parser.add_argument("--select", action="store_true")
    options = parser.parse_args()

    configure_logging()
    log = logging.getLogger("stand_in")
    log.info("level %s", logging.getLevelName(log.getEffectiveLevel()))
    log.debug("stdlib debug")
    loguru_logger.debug("loguru debug")
    logging.getLogger("redsun.stand_in").info("from the redsun tree")

    print(f"identity {identity()}", flush=True)
    if options.select:
        stop_on_request()
        ready()
        waiting, _ = os.pipe()
        try:
            select.select([waiting], [], [])
        except KeyboardInterrupt:
            pass
    elif options.blocking:
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
