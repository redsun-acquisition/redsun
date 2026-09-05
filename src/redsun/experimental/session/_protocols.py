from __future__ import annotations

from abc import abstractmethod
from typing import (
    TYPE_CHECKING,
    Any,
    NoReturn,
    Protocol,
    Self,
    TypeVar,
    runtime_checkable,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from contextlib import AbstractContextManager

    from in_n_out import Store

    from redsun.experimental.view._placement import Placement

__all__ = [
    "AttachableComponent",
    "BuildableSession",
    "DesktopSession",
    "NamedComponent",
    "Serializable",
]

WindowT_co = TypeVar("WindowT_co", covariant=True)


@runtime_checkable
class NamedComponent(Protocol):
    """A component that knows the name it was declared under.

    Every component clears this, presenters and views alike. A session may
    declare two components of one class, and the declared name is the only
    thing telling them apart, so one that discards the name it was constructed
    with cannot be identified in anything it emits.

    Declared as a read-only property because the framework only reads it: a
    plain instance attribute, a class attribute or a property all satisfy it.
    """

    @property
    def name(self) -> str:
        """Identity key of the component."""
        ...


@runtime_checkable
class AttachableComponent(NamedComponent, Protocol):
    """A component the frontend can attach, and where it asks to go.

    ``placement`` is the whole of the difference between a view and a
    presenter, and it is what the frontend reads to attach the view.
    Answering it from the class rather than from a value assigned in
    ``__init__`` lets a session refuse a view its frontend cannot attach
    before anything is built.
    """

    @property
    def placement(self) -> Placement:
        """Where the component asks to be attached."""
        ...


@runtime_checkable
class BuildableSession(Protocol):
    """The steps a session's build runs, each one a method of its own.

    ``build`` calls them in the order they are written here and does nothing
    else, so what a session varies is a step rather than the sequence. A
    session bound to no toolkit answers ``start_runtime`` and ``present`` with
    nothing, and one bound to a toolkit fills exactly those two: what has to
    exist before a component can be constructed, and how what was built is
    assembled into whatever shows it.

    Every step takes nothing and returns nothing. What a step needs it reads
    from the session, and what it leaves it leaves on the session, so a step
    can be replaced without the ones around it knowing. A step taking
    something that has to be given back registers how with `on_release` at the
    moment it takes it, and `shutdown` runs those in reverse, so a teardown is
    the build read backwards and a build that fails runs the releases its
    finished steps earned.

    Inherit it rather than satisfying it structurally. The members are
    abstract, so a session missing one is refused when it is constructed and a
    type checker refuses it too.

    ``__slots__`` is empty here because a body omitting it gives a ``__dict__``
    to every class that inherits it, and `redsun.experimental.Session` declares
    its own.
    """

    __slots__ = ()

    @abstractmethod
    def build(self) -> Self:
        """Run every step below, in order, and return the built session."""
        ...

    @abstractmethod
    def read_configuration(self) -> None:
        """Merge the sources, install the hooks, and read the declarations."""
        ...

    @abstractmethod
    def start_runtime(self) -> None:
        """Put in place what a component may not be constructed without."""
        ...

    @abstractmethod
    def build_devices(self) -> None:
        """Construct the devices, which are built from no other component."""
        ...

    @abstractmethod
    def open_registry(self) -> None:
        """Open the store the components are built out of, and fill it."""
        ...

    @abstractmethod
    def build_presenters(self) -> None:
        """Construct the presenter layer, in the order it depends in."""
        ...

    @abstractmethod
    def build_views(self) -> None:
        """Construct the view layer, in the order it depends in."""
        ...

    @abstractmethod
    def seal(self) -> None:
        """Check what was built, then close the session to further building."""
        ...

    @abstractmethod
    def apply_wiring(self) -> None:
        """Connect the ports the class declares, then those the file names."""
        ...

    @abstractmethod
    def present(self) -> None:
        """Assemble what was built into whatever shows it."""
        ...

    @abstractmethod
    def log_summary(self) -> None:
        """Say what the build made, counted against what was declared."""
        ...

    @abstractmethod
    def make_store(self) -> Store:
        """Return the registry ``open_registry`` fills and builds out of."""
        ...

    @abstractmethod
    def open_span(self) -> AbstractContextManager[Callable[[str], None]]:
        """Return the span the build announces its steps to."""
        ...

    @abstractmethod
    def on_release(self, release: Callable[[], None]) -> None:
        """Register how to give something back, as the step takes it."""
        ...

    @abstractmethod
    def shutdown(self) -> None:
        """Run every registered release, in the reverse of the order taken."""
        ...


@runtime_checkable
class DesktopSession(BuildableSession, Protocol[WindowT_co]):
    """A session whose views are attached to a window and shown on a screen.

    The window's type is the parameter, since it is the toolkit's and no two
    toolkits share one: a session built on Qt satisfies
    ``DesktopSession[QMainWindow]``.

    ``main_window`` is a property here, so it is a data descriptor in every
    implementer's method resolution order: answer it with a property of its
    own, never by assigning ``self.main_window`` in ``__init__``.
    """

    __slots__ = ()

    @property
    @abstractmethod
    def main_window(self) -> WindowT_co:
        """The window the views are attached to."""
        ...

    @abstractmethod
    def run(self) -> NoReturn:
        """Build, show the window, and hand over to the event loop."""
        ...


@runtime_checkable
class Serializable(Protocol):
    """A component that supplies the configuration entry rebuilding it.

    ``serialize`` returns the keyword arguments the component's own entry
    would carry. The session writes them under that component's name and
    nowhere else, so a component reaches no entry but its own, and the next
    session reads back what this one wrote.

    Implementing it is optional, and a component that leaves it out keeps
    whatever the configuration already said about it.

    A value that moves on its own, such as a stage position or a frame count,
    is not a constructor argument and does not belong in the result.
    """

    def serialize(self) -> Mapping[str, Any]:
        """Return the keyword arguments this component would be rebuilt from."""
        ...
