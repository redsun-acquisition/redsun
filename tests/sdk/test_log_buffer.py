"""The session log buffer retains recent records and announces each one."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest

from redsun.log import BufferHandler, log_buffer, logger, service_of, set_level

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture
def buffer() -> Iterator[BufferHandler]:
    """Yield the session buffer, emptied, with the logger passing every level to it."""
    held = log_buffer()
    held.clear()
    level = logger.level
    set_level(logging.DEBUG)
    yield held
    logger.setLevel(level)
    held.clear()


def _record(
    level: int, message: str, name: str = "redsun", created: float | None = None
) -> logging.LogRecord:
    record = logging.LogRecord(name, level, __file__, 0, message, None, None)
    if created is not None:
        record.created = created
    return record


def test_the_buffer_is_installed_on_the_redsun_logger() -> None:
    """It is installed alongside the stdout handler, not by a caller."""
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


def test_a_service_logging_heavily_drops_only_its_own_records() -> None:
    """An application warning outlives a flood of service records."""
    handler = BufferHandler(capacity=10_000, service_capacity=2_000)
    handler.emit(_record(logging.WARNING, "application warning"))

    for i in range(12_000):
        handler.emit(_record(logging.INFO, f"flood {i}", "redsun.service.cam"))

    assert [r.getMessage() for r in handler.records] == ["application warning"]
    kept = handler.service_records("cam")
    assert len(kept) == 2_000
    assert kept[-1].getMessage() == "flood 11999"


def test_service_records_are_read_per_service_or_merged_by_time() -> None:
    handler = BufferHandler(capacity=10, service_capacity=10)
    handler.emit(_record(logging.INFO, "stage 1", "redsun.service.stage", 1.0))
    handler.emit(_record(logging.INFO, "cam 2", "redsun.service.cam.caproto", 2.0))
    handler.emit(_record(logging.INFO, "stage 3", "redsun.service.stage", 3.0))

    assert handler.services == ("stage", "cam")
    assert [r.getMessage() for r in handler.service_records("stage")] == [
        "stage 1",
        "stage 3",
    ]
    assert [r.getMessage() for r in handler.service_records()] == [
        "stage 1",
        "cam 2",
        "stage 3",
    ]
    assert handler.records == ()


@pytest.mark.parametrize(
    ("name", "service"),
    [
        ("redsun", None),
        ("redsun.containers", None),
        ("redsun.service.cam", "cam"),
        ("redsun.service.cam.caproto.ioc", "cam"),
        ("redsun.services", None),
    ],
)
def test_a_record_names_the_service_it_came_from(
    name: str, service: str | None
) -> None:
    assert service_of(_record(logging.INFO, "", name)) == service


def test_each_record_is_announced() -> None:
    handler = BufferHandler(capacity=10)
    seen: list[logging.LogRecord] = []
    handler.sig_record.connect(seen.append)

    handler.emit(_record(logging.ERROR, "announced"))

    assert [r.getMessage() for r in seen] == ["announced"]


def test_clear_drops_every_record() -> None:
    handler = BufferHandler(capacity=10)
    handler.emit(_record(logging.INFO, "gone"))
    handler.emit(_record(logging.INFO, "gone too", "redsun.service.cam"))

    handler.clear()

    assert (handler.records, handler.services) == ((), ())
