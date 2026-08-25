"""The session log buffer retains recent records and announces each one."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest

from redsun.log import BufferHandler, log_buffer

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture
def buffer() -> Iterator[BufferHandler]:
    held = log_buffer()
    held.clear()
    yield held
    held.clear()


def _record(level: int, message: str) -> logging.LogRecord:
    return logging.LogRecord("redsun", level, __file__, 0, message, None, None)


def test_the_buffer_is_installed_on_the_redsun_logger() -> None:
    """It is configured alongside the stdout handlers, not by a caller."""
    assert log_buffer() in logging.getLogger("redsun").handlers


def test_the_buffer_is_the_same_object_every_time() -> None:
    assert log_buffer() is log_buffer()


def test_records_are_retained_in_order(buffer: BufferHandler) -> None:
    logging.getLogger("redsun").info("first")
    logging.getLogger("redsun").warning("second")

    assert [r.getMessage() for r in buffer.records] == ["first", "second"]


def test_every_level_is_retained(buffer: BufferHandler) -> None:
    """The buffer carries no filter: the stdout handlers split levels, it does not."""
    logger = logging.getLogger("redsun")
    for level in (
        logging.DEBUG,
        logging.INFO,
        logging.WARNING,
        logging.ERROR,
        logging.CRITICAL,
    ):
        logger.log(level, "message")

    assert [r.levelno for r in buffer.records] == [
        logging.DEBUG,
        logging.INFO,
        logging.WARNING,
        logging.ERROR,
        logging.CRITICAL,
    ]


def test_the_buffer_is_bounded() -> None:
    """A long session drops the oldest records rather than growing without limit."""
    handler = BufferHandler(capacity=3)

    for i in range(5):
        handler.emit(_record(logging.INFO, str(i)))

    assert [r.getMessage() for r in handler.records] == ["2", "3", "4"]


def test_each_record_is_announced() -> None:
    handler = BufferHandler(capacity=10)
    seen: list[logging.LogRecord] = []
    handler.sig_record.connect(seen.append)

    handler.emit(_record(logging.ERROR, "announced"))

    assert [r.getMessage() for r in seen] == ["announced"]


def test_clear_drops_every_record() -> None:
    handler = BufferHandler(capacity=10)
    handler.emit(_record(logging.INFO, "gone"))

    handler.clear()

    assert handler.records == ()
