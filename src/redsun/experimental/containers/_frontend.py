from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from collections.abc import Mapping

    from redsun.experimental.view._placement import Placement

__all__ = ["Frontend"]


class Frontend:
    """The toolkit an application is built against.

    ``requires`` pairs each `redsun.experimental.Placement` the frontend
    attaches with the toolkit type it demands of the view asking for it. A view
    asking for a placement the frontend does not list, or one whose class is
    not the type its placement demands, is refused before it is built. The
    table is all a container needs; the placements themselves and the attaching
    live in the frontend's own package.

    An empty table constrains nothing, which is what an application that names
    no toolkit gets.
    """

    requires: ClassVar[Mapping[type[Placement], type]] = {}

    @classmethod
    def check_placement(
        cls, view: type | object, placement: Placement, where: str
    ) -> None:
        """Confirm the frontend attaches *placement*, and *view* is what it demands.

        *view* is the class before anything is built and the instance
        afterwards; either answers the question, since the demand is on the
        class.

        Raises
        ------
        TypeError
            If the frontend lists what it attaches and this is not one of
            them, or if the view is not the toolkit type that placement
            demands.
        """
        if not cls.requires:
            return
        asked = type(placement)
        required = cls.requires.get(asked)
        if required is None:
            known = ", ".join(sorted(p.__name__ for p in cls.requires))
            raise TypeError(
                f"{where} asks to be attached as {asked.__name__!r}, which "
                f"{cls.__name__} does not attach. It attaches: {known}."
            )
        candidate = view if isinstance(view, type) else type(view)
        if not issubclass(candidate, required):
            raise TypeError(
                f"{where} asks to be attached as {asked.__name__!r}, which needs "
                f"a {required.__name__}, but {candidate.__name__} is not one"
            )
