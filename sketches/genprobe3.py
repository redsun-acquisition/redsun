from __future__ import annotations

from typing import Annotated as A
from typing import Any, Generic, Protocol, TypeVar


class Dependency(Protocol):
    timeout: float


class ConcreteDep:
    timeout: float = 1.0


class NotADep: ...


D = TypeVar("D", bound=Dependency)


class Presenter: ...


class MyPresenter(Presenter, Generic[D]):
    def __init__(self, name: str, /, dependency: D) -> None: ...


class Declare:
    def __init__(self, **kwargs: Any) -> None: ...


class Root(Generic[D]):
    dependency: D


class AppContainer(Generic[D]):
    """Annotation-only declarations, resolved at build; no descriptor."""

    def __getattr__(self, name: str) -> Any: ...


# ---- annotation-only declaration on a generic app
class GenericApp(AppContainer[D], Generic[D]):
    p: A[MyPresenter[D], Declare(max_digits=6)]

    def wire(self) -> None:
        reveal_type(self.p)


class MyApp(GenericApp[ConcreteDep]): ...


reveal_type(MyApp().p)
reveal_type(GenericApp[ConcreteDep]().p)

# does __getattr__ swallow an undeclared name (it should) ...
reveal_type(MyApp().nonexistent)

# ... while the bound is still enforced on the app parameter?
bad: GenericApp[NotADep]
