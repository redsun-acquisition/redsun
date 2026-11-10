"""An executor's calls are typed as the function's result.

Never imported or executed; checked by the project's normal mypy invocation.
"""

from __future__ import annotations

from typing import assert_type

from redsun import Session
from redsun.compute import Future, ThreadExecutor
from redsun.compute._pool import Pool


def check(executor: ThreadExecutor) -> None:
    assert_type(executor.submit(len, "abc"), Future[int])
    assert_type(executor.pool_type, type[Pool])


async def check_run(executor: ThreadExecutor) -> None:
    assert_type(await executor.run(len, "abc"), int)


class Typed(Session):
    compute = {"preset": "throughput", "cores": 4}  # noqa: RUF012


class Word(Session):
    compute = "latency"
