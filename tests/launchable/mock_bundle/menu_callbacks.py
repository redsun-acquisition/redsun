"""Callbacks the `actions` section of a test session names by `module:function`."""

from __future__ import annotations

from typing import NewType, Protocol

Executed = NewType("Executed", "list[str]")
"""What the commands ran, which a presenter of the session provides."""


def note(executed: Executed) -> None:
    """Record that the command ran."""
    executed.append("note")


def note_twice(executed: Executed) -> None:
    """Record twice, so two entries of one section are told apart."""
    executed.extend(["twice", "twice"])


class HasRecord(Protocol):
    """What a component offers when it keeps a list of what ran."""

    record: list[str]


def note_by_shape(recorder: HasRecord) -> None:
    """Record that the command ran, with the component found by its shape."""
    recorder.record.append("shape")
