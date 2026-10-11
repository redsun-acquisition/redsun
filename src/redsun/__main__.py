"""Run the `redsun` command as `python -m redsun`."""

from __future__ import annotations

import sys

from redsun._cli import main

if __name__ == "__main__":
    sys.exit(main())
