from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import (
    TYPE_CHECKING,
    Annotated,
    Any,
    NewType,
    TypeAlias,
    TypeVar,
    get_args,
    get_origin,
)

from redsun._structural import members, methods, problems, satisfies

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from typing_extensions import TypeForm

    from redsun.experimental.containers._declarations import Key

__all__ = [
    "Devices",
    "DevicesOf",
    "Every",
    "Maybe",
    "One",
    "Question",
    "Requires",
    "RequiresMaybe",
    "RequiresOne",
    "Satisfying",
    "key_for",
    "question_of",
]


@dataclass(frozen=True)
class Every:
    """Marks a parameter as a question about the session rather than a value.

    The container answers it with every component satisfying the annotated
    protocol.
    """


@dataclass(frozen=True)
class One(Every):
    """Marks a question exactly one component must answer."""


@dataclass(frozen=True)
class Maybe(Every):
    """Marks a question at most one component may answer."""


@dataclass(frozen=True)
class Devices(Every):
    """Marks a question the devices answer rather than the components."""


P = TypeVar("P")

Requires: TypeAlias = Annotated[Mapping[str, P], Every()]
"""Every component of the session that satisfies *P*, by name.

```python
@runtime_checkable
class Resettable(Protocol):
    def reset(self) -> None: ...


class SessionPresenter:
    def __init__(self, name: str, /, resettable: Requires[Resettable]) -> None:
        self._resettable = resettable
```

The set is not known until every component exists, so the parameter is a live
view: hold it and read it when the component runs. Reading it while the
component is built raises `LookupError`.

A component asking this sees itself if it satisfies *P* too. Ask
`RequiresOne` or `RequiresMaybe` instead when one component is wanted rather
than a census.
"""

RequiresOne: TypeAlias = Annotated[P, One()]
"""The single component of the session that satisfies *P*.

```python
class RoiWidget:
    def __init__(self, name: str, /, camera: RequiresOne[HasCamera]) -> None:
        self._camera = camera
```

Unlike `Requires`, this is an ordinary dependency: the component arrives built,
and whatever provides it is created first. The session must hold exactly one
answer, so a session with none or with several fails to build.

*P* must declare at least one method. Which component answers is decided
before anything is built, and a data member assigned in ``__init__`` cannot be
seen that early.
"""

RequiresMaybe: TypeAlias = Annotated[P | None, Maybe()]
"""The single component of the session that satisfies *P*, if there is one.

```python
class MotorPresenter:
    def __init__(self, name: str, /, roi: RequiresMaybe[HasRoi] = None) -> None:
        self._roi = roi
```

As `RequiresOne`, except that an empty session answers with ``None``. Several
answers are still an error, because the parameter has room for one.
"""

DevicesOf: TypeAlias = Annotated[Mapping[str, P], Devices()]
"""Every device of the session that satisfies *P*, by name.

```python
@runtime_checkable
class MotorProtocol(Protocol):
    async def set(self, value: float) -> None: ...


class MotorPresenter:
    def __init__(self, name: str, /, motors: DevicesOf[MotorProtocol]) -> None:
        self._motors = motors
```

Unlike `Requires`, this is not a live view: devices are built before anything
asks about them, so the mapping arrives complete and may be read while the
component is built.

Ask for `redsun.experimental.DeviceMapping` instead to receive every device,
unfiltered.
"""


@dataclass(frozen=True)
class Question:
    """A protocol a component asks about, and how many answers it expects."""

    protocol: type
    marker: Every

    @property
    def kind(self) -> str:
        """The marker's name, lowercased."""
        return type(self.marker).__name__.lower()

    def __str__(self) -> str:
        return f"{self.kind} {self.protocol.__name__!r}"


class Satisfying(Mapping[str, Any]):
    """Live view of the components satisfying a protocol.

    Raises
    ------
    LookupError
        If read before every component exists.
    """

    def __init__(
        self,
        protocol: type,
        components: Mapping[str, object],
        ready: Callable[[], bool],
    ) -> None:
        self._protocol = protocol
        self._components = components
        self._ready = ready

    def _complete(self) -> dict[str, Any]:
        if not self._ready():
            raise LookupError(
                f"the components satisfying {self._protocol.__name__!r} are not "
                "known until every component exists. Hold this view and read it "
                "when the component runs, rather than copying it while it is "
                "built."
            )
        return {
            name: component
            for name, component in self._components.items()
            if satisfies(component, self._protocol)
        }

    @property
    def rejected(self) -> dict[str, list[str]]:
        """Why each component that nearly matched was left out.

        Only components carrying some of the protocol's members appear, so a
        component missing all of them does not drown out a near miss.
        """
        wanted = members(self._protocol)
        near: dict[str, list[str]] = {}
        for name, component in self._components.items():
            reasons = problems(component, self._protocol)
            if reasons and any(hasattr(component, member) for member in wanted):
                near[name] = reasons
        return near

    def __getitem__(self, key: str) -> Any:
        return self._complete()[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._complete())

    def __len__(self) -> int:
        return len(self._complete())

    def __repr__(self) -> str:
        state = "live" if self._ready() else "pending"
        return f"Satisfying({self._protocol.__name__}, {state})"


def question_of(hint: TypeForm[Any]) -> Question | None:
    """Return what *hint* asks about the session, or ``None`` if it asks for a value.

    Raises
    ------
    TypeError
        If *hint* carries a marker but is not shaped the way that marker
        requires, or names a protocol that cannot be asked about.
    """
    if get_origin(hint) is not Annotated:
        return None
    inner, *metadata = get_args(hint)
    markers = [marker for marker in metadata if isinstance(marker, Every)]
    if not markers:
        return None
    marker = markers[0]
    protocol = _protocol(hint, inner, marker)
    _validate(protocol, marker)
    return Question(protocol, marker)


def _protocol(hint: TypeForm[Any], inner: Any, marker: Every) -> type:
    if isinstance(marker, One):
        if not isinstance(inner, type):
            raise TypeError(
                f"{hint} is marked with One() but is not a protocol. Write "
                "'RequiresOne[P]'."
            )
        return inner
    if isinstance(marker, Maybe):
        options = [arg for arg in get_args(inner) if arg is not type(None)]
        if len(options) != 1 or not isinstance(options[0], type):
            raise TypeError(
                f"{hint} is marked with Maybe() but is not a 'P | None'. Write "
                "'RequiresMaybe[P]'."
            )
        return options[0]
    args = get_args(inner)
    if get_origin(inner) is not Mapping or len(args) != 2 or args[0] is not str:
        alias = "DevicesOf" if isinstance(marker, Devices) else "Requires"
        raise TypeError(
            f"{hint} is marked with {type(marker).__name__}() but is not a "
            f"'Mapping[str, P]'. Write '{alias}[P]', which expands to the right "
            "shape."
        )
    return args[1]  # type: ignore[no-any-return]


def _validate(protocol: type, marker: Every) -> None:
    if not getattr(protocol, "_is_runtime_protocol", False):
        raise TypeError(
            f"{getattr(protocol, '__name__', protocol)!r} cannot be asked about: "
            "a protocol is matched structurally, and only one decorated with "
            "'typing.runtime_checkable' declares that it is meant to be."
        )
    if isinstance(marker, (One, Maybe)) and not methods(protocol):
        raise TypeError(
            f"{protocol.__name__!r} declares no method, so which component "
            "answers cannot be decided before they are built. Ask with "
            f"'Requires[{protocol.__name__}]', which is answered afterwards."
        )


_SUPERTYPES: dict[str, Any] = {
    "every": Mapping[str, Any],
    "devices": Mapping[str, Any],
}
_KEYS: dict[Question, Key] = {}


def key_for(question: Question) -> Key:
    """Return the dependency key standing for *question*.

    dishka discards the metadata of an ``Annotated`` type when it keys on it, so
    a question would otherwise be indistinguishable from a plain value of the
    same shape.
    """
    if question not in _KEYS:
        _KEYS[question] = NewType(
            f"{question.kind.capitalize()}_{question.protocol.__name__}",
            _SUPERTYPES.get(question.kind, object),
        )
    return _KEYS[question]
