from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from redsun.experimental._placement import Placement

__all__ = ["Frontend", "check_placement"]


class Frontend:
    """The toolkit an application is built against.

    ``placements`` is the vocabulary of `redsun.experimental.Placement` the
    frontend knows how to attach, so a view asking for anything else is
    refused before it is built. Listing them is all a container needs; the
    placements themselves, the attaching, and the toolkit type each placement
    demands live in the frontend's own package.

    Listing none constrains nothing, which is what an application that names
    no toolkit gets.
    """

    placements: ClassVar[frozenset[type[Placement]]] = frozenset()


def check_placement(placement: Placement, frontend: type[Frontend], where: str) -> None:
    """Confirm *frontend* knows how to attach *placement*.

    Raises
    ------
    TypeError
        If the frontend lists the placements it attaches and this is not one.
    """
    if not frontend.placements or type(placement) in frontend.placements:
        return
    known = ", ".join(sorted(p.__name__ for p in frontend.placements))
    raise TypeError(
        f"{where} asks to be attached as {type(placement).__name__!r}, which "
        f"{frontend.__name__} does not attach. It attaches: {known}."
    )
