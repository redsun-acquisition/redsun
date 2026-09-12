from __future__ import annotations

from dataclasses import dataclass

__all__ = ["Placement"]


@dataclass(frozen=True)
class Placement:
    """Where a view asks to be attached.

    A placement is an intent and nothing more: it names no toolkit type, and
    this module defines no concrete one. Each frontend declares the placements
    it understands in its own package, next to the code that attaches them, so
    a window concept such as a dock never reaches a session that has no
    window. A frontend attaches the placements it lists in
    `redsun.experimental.Frontend.placements` and refuses the rest.

    Declaring one is what makes a component a view. A presenter attaches
    nowhere and declares none.
    """
