from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Generic, Protocol, TypeVar, cast


class Dependency(Protocol):
    timeout: float


class ConcreteDep:
    timeout: float = 1.0


class OtherDep:
    timeout: float = 2.0


D = TypeVar("D", bound=Dependency)
T = TypeVar("T")


class Presenter:
    pass


class MyPresenter(Presenter, Generic[D]):
    def __init__(self, name: str, /, dependency: D) -> None: ...


@dataclass
class RootDependency:
    dependency: Dependency


@dataclass
class MyRoot(RootDependency):
    dependency: ConcreteDep


@dataclass
class OtherRoot(RootDependency):
    dependency: OtherDep


class NotARoot:
    pass


RD = TypeVar("RD", bound=RootDependency)


class _Field(Generic[T]):
    def __get__(self, obj: object, owner: Any = None) -> T: ...


def declare_presenter(cls: type[T], /, **kwargs: Any) -> T:
    return cast("T", _Field())


def declare_field(cls: type[Any], /, **kwargs: Any) -> _Field[Any]:
    return _Field()


class AppContainer(Generic[RD]):
    pass


# ---- CASE A: bare inference, as written in dishka_test.py
class AppA(AppContainer[MyRoot]):
    p = declare_presenter(MyPresenter)


reveal_type(AppA().p)


# ---- CASE B: explicit annotation naming the concrete root
class AppB(AppContainer[MyRoot]):
    p: MyPresenter[ConcreteDep] = declare_presenter(MyPresenter)


reveal_type(AppB().p)


# ---- CASE B2: annotation naming a root the app does NOT declare
class AppB2(AppContainer[MyRoot]):
    p: MyPresenter[OtherDep] = declare_presenter(MyPresenter)


reveal_type(AppB2().p)


# ---- CASE C: descriptor whose parameter mentions the OWNER's TypeVar
class GenericApp(AppContainer[RD], Generic[RD]):
    p: _Field[MyPresenter[RD]] = declare_field(MyPresenter)


reveal_type(GenericApp[MyRoot]().p)
reveal_type(GenericApp[OtherRoot]().p)


# ---- CASE D: TypeVar used in a class-body VALUE expression
class AppD(AppContainer[MyRoot], Generic[RD]):
    p = declare_presenter(MyPresenter[RD])


# ---- CASE E: is the TypeVar bound enforced on the app parameter?
class AppE(AppContainer[NotARoot]):
    pass


# ---- CASE F: does anything check that the root supplies what MyPresenter needs?
class AppF(AppContainer[OtherRoot]):
    p: MyPresenter[ConcreteDep] = declare_presenter(MyPresenter)
