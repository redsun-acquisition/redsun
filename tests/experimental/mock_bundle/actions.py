"""Module-level contributions a session's ``actions`` section may name."""

from __future__ import annotations

executed: list[str] = []


def note() -> None:
    """Record that the command ran, needing nothing from the session."""
    executed.append("note")


def note_twice() -> None:
    """Record twice, so two entries of one section are told apart."""
    executed.extend(["twice", "twice"])
