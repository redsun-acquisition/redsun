from __future__ import annotations

from dataclasses import dataclass

__all__ = ["Placement"]


@dataclass(frozen=True)
class Placement:
    """Where a view asks to be attached.

    A placement names no toolkit type, and this module defines no concrete
    one. Each frontend declares the placements it understands in its own
    package. A frontend attaches the placements it lists in
    `redsun.Frontend.requires` and refuses the rest.

    Declaring one is what makes a component a view. A presenter attaches
    nowhere and declares none.
    """
