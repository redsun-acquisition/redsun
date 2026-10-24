"""`RunEngine` takes a function for its `scan_id`, never `None`.

Never imported or executed; checked by the project's normal mypy invocation.
The engine calls `scan_id_source` at every run it opens, so `None` must be
refused where it is passed.
"""

from __future__ import annotations

from redsun.engine import RunEngine

RunEngine(scan_id_source=None)  # type: ignore[arg-type]
