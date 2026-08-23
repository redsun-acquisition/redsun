from __future__ import annotations

from typing import Any, Generic, Protocol, TypeVar, cast


class Dependency(Protocol):
    timeout: float


class ConcreteDep:
    timeout: float = 1.0


class OtherDep:
    timeout: float = 2.0


class NotADep:
    pass


D = TypeVar("D", bound=Dependency)
D2 = TypeVar("D2", bound=Dependency)
T = TypeVar("T")


class Presenter: ...


class MyPresenter(Presenter, Generic[D]):
    def __init__(self, name: str, /, dependency: D) -> None: ...


class OtherPresenter(Presenter, Generic[D]):
    def __init__(self, name: str, /, dependency: D) -> None: ...


class _Field(Generic[T]):
    def __get__(self, obj: object, owner: Any = None) -> T:
        raise NotImplementedError


def declare(cls: type[Any], /, **kwargs: Any) -> _Field[Any]:
    return _Field()


# ---- the root is itself generic, instead of a dataclass of concrete members
class Root(Generic[D]):
    dependency: D


RD = TypeVar("RD", bound=Root[Any])


class AppContainer(Generic[RD]): ...


# ---- CASE G: app generic over the dependency, root parameterized by it
class GenericApp(AppContainer[Root[D]], Generic[D]):
    p: _Field[MyPresenter[D]] = declare(MyPresenter)


reveal_type(GenericApp[ConcreteDep]().p)
reveal_type(GenericApp[OtherDep]().p)


# ---- CASE G2: is the presenter's own bound enforced through the app?
class BadApp(GenericApp[NotADep]): ...


x: GenericApp[NotADep]


# ---- CASE H: two dependencies, two parameters
class Root2(Generic[D, D2]):
    first: D
    second: D2


class AppContainer2(Generic[T]): ...


class TwoDepApp(AppContainer2[Root2[D, D2]], Generic[D, D2]):
    p: _Field[MyPresenter[D]] = declare(MyPresenter)
    q: _Field[OtherPresenter[D2]] = declare(OtherPresenter)


reveal_type(TwoDepApp[ConcreteDep, OtherDep]().p)
reveal_type(TwoDepApp[ConcreteDep, OtherDep]().q)


# ---- CASE I: concrete app, the shape a real application would have
class MyApp(GenericApp[ConcreteDep]): ...


reveal_type(MyApp().p)


# ---- CASE J: can the field infer its parameter from the declared class,
#              so the author does not repeat MyPresenter[D] in the annotation?
def declare_inferring(cls: type[T], /, **kwargs: Any) -> _Field[T]:
    return cast("_Field[T]", _Field())


class InferApp(AppContainer[Root[D]], Generic[D]):
    p = declare_inferring(MyPresenter)


reveal_type(InferApp[ConcreteDep]().p)
