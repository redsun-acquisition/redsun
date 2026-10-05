"""Module-level contributions a session's `actions` section may name."""

from __future__ import annotations

from typing import NewType

Executed = NewType("Executed", "list[str]")
"""What the commands ran, which a presenter of the session provides."""


def note(executed: Executed) -> None:
    """Record that the command ran."""
    executed.append("note")


def note_twice(executed: Executed) -> None:
    """Record twice, so two entries of one section are told apart."""
    executed.extend(["twice", "twice"])
