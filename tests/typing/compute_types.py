"""`ThreadExecutor` keeps the result type of the call it runs.

Never imported or executed; checked by the project's normal mypy invocation.
"""

from __future__ import annotations

from concurrent.futures import Future
from typing import assert_type

from redsun.compute import ThreadExecutor

assert_type(ThreadExecutor(1).submit(pow, 2, 3), Future[int])
assert_type(ThreadExecutor(1).native_threads, int)
