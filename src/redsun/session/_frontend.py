from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from collections.abc import Mapping

    from redsun.ports import SlotThread
    from redsun.view import Column, Placement, Row, Tabs, WindowLayout

__all__ = ["Frontend"]


class Frontend:
    """The toolkit an application is built against.

    `requires` pairs each `redsun.Placement` the frontend
    attaches with the toolkit type it demands of the view asking for it. A view
    asking for a placement the frontend does not list, or one whose class is
    not the type its placement demands, is refused before it is built. The
    placements themselves and the attaching live in the frontend's own
    package.

    An empty table constrains nothing, which is what an application that names
    no toolkit gets.

    `regions`, `hides` and `region_of` say how a window layout maps onto the
    frontend's window; a frontend leaving them empty accepts none.

    `thread_of` says where the slots of a component run when the component
    does not say. A slot held for a thread is called there once that thread
    calls `psygnal.emit_queued`, which a session built on the frontend does
    from the toolkit's event loop.
    """

    requires: ClassVar[Mapping[type[Placement], type]] = {}

    regions: ClassVar[Mapping[str, type[Row | Column | Tabs]]] = {}
    """The regions of the window a layout fills, each with how a view the layout leaves out joins it.

    Empty here: a frontend listing no region accepts no window layout.
    """

    hides: ClassVar[bool] = False
    """Whether a window layout may start a view hidden."""

    @classmethod
    def check_view(cls, view: type, where: str) -> None:
        """Refuse a view class this frontend cannot build.

        Runs where the view is declared, beside `check_placement`. Nothing is
        refused here; a frontend constraining how its views are constructed
        overrides it.

        Raises
        ------
        TypeError
            In an override, naming what *view* lacks.
        """

    @classmethod
    def thread_of(cls, consumer: object) -> SlotThread:
        """Return the thread the slots of *consumer* run on when nothing else says.

        Asked after the slot itself and the class of *consumer*. `None`
        here: the slot runs on the thread that emits.
        """
        return None

    @classmethod
    def read_placement(cls, value: object) -> Placement:
        """Return the placement a session file's *value* names, in this frontend's words.

        A frontend that attaches views overrides it; this one reads no word.

        Raises
        ------
        ValueError
            Always, naming the frontend.
        """
        raise ValueError(
            f"{cls.__name__} reads no placement from a session file; give a "
            "placement object in Python instead"
        )

    @classmethod
    def region_of(cls, placement: Placement) -> tuple[str, str | None] | None:
        """Return the region *placement* asks for and the group it suggests, or `None` outside any region.

        A frontend with regions overrides it; this one places nothing in one.
        """
        return None

    @classmethod
    def key_problems(cls, key: str) -> list[str]:
        """Return what is wrong with *key* in this frontend's spelling; nothing here."""
        return []

    @classmethod
    def canonical_key(cls, key: str) -> str:
        """Return *key* as this frontend writes it, so two spellings of one key compare equal.

        *key* unchanged here.
        """
        return key

    @classmethod
    def layout_problems(cls, layout: WindowLayout) -> list[str]:
        """Return what this frontend cannot show of *layout*, one line each as `layout.key: what`."""
        if not cls.regions:
            return [f"layout: {cls.__name__} lays out no window"]
        known = ", ".join(repr(region) for region in cls.regions)
        problems = [
            f"layout.{section}.{region}: {cls.__name__} has no region "
            f"{region!r}; it has {known}"
            for section, keys in (("regions", layout.regions), ("sizes", layout.sizes))
            for region in keys
            if region not in cls.regions
        ]
        if layout.hidden and not cls.hides:
            problems.append(f"layout.hidden: {cls.__name__} starts no view hidden")
        return problems

    @classmethod
    def check_placement(
        cls, view: type | object, placement: Placement, where: str
    ) -> None:
        """Confirm the frontend attaches *placement*, and *view* is what it demands.

        Parameters
        ----------
        view
            The class before anything is built and the instance afterwards.
            Either answers the question, the demand being on the class.
        placement
            Where the view asks to be attached.
        where
            How to name the view in a refusal, such as
            `"view 'panel'"`.

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
