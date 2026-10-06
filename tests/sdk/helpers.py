"""Helpers the SDK tests share."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest


def messages(caplog: pytest.LogCaptureFixture, level: int) -> list[str]:
    """Return the text of the records logged at exactly *level*."""
    return [r.getMessage() for r in caplog.records if r.levelno == level]
