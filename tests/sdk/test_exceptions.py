from __future__ import annotations

import pytest

from redsun.engine._exceptions import (
    BlueskyException,
    InvalidState,
    StatusTimeoutError,
    UnknownStatusFailure,
    WaitTimeoutError,
)


@pytest.mark.parametrize(
    ("exc_type", "extra_base"),
    [
        (InvalidState, RuntimeError),
        (UnknownStatusFailure, Exception),
        (StatusTimeoutError, TimeoutError),
        (WaitTimeoutError, TimeoutError),
    ],
)
def test_exception_hierarchy(
    exc_type: type[BlueskyException], extra_base: type[BaseException]
) -> None:
    """Every engine exception is catchable as BlueskyException AND its stdlib base."""
    assert issubclass(exc_type, BlueskyException)
    assert issubclass(exc_type, extra_base)
    with pytest.raises(BlueskyException):
        raise exc_type("boom")


def test_status_timeout_is_distinct_from_wait_timeout() -> None:
    """The two timeout flavours must not be confused with one another."""
    assert not issubclass(StatusTimeoutError, WaitTimeoutError)
    assert not issubclass(WaitTimeoutError, StatusTimeoutError)
