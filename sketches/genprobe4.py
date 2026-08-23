"""Probe: does TypeForm replace `Any` for the type-expression parameters?

The sketch passes type expressions around constantly - `provided: Any`,
`available: Mapping[Any, AppScope]`, `hint: Any`. PEP 747's TypeForm is what
those actually are.
"""

from __future__ import annotations

from typing import Annotated, Any, NewType

from typing_extensions import TypeForm

MotorReadings = NewType("MotorReadings", dict)


def optional_arg(hint: TypeForm[Any]) -> TypeForm[Any] | None:
    """`X` for `X | None`."""


def injectable(cls: type, cfg: dict[str, Any]) -> dict[str, TypeForm[Any]]:
    """Constructor parameters the graph must fill."""


def synthesize(
    fn: Any, params: dict[str, TypeForm[Any]], returns: TypeForm[Any], name: str
) -> Any:
    """Give *fn* the public signature `(**params) -> returns`."""


# the values actually passed at the call sites
a: TypeForm[Any] = int
b: TypeForm[Any] = MotorReadings
c: TypeForm[Any] = dict[str, float]
d: TypeForm[Any] = int | None
e: TypeForm[Any] = Annotated[int, "meta"]
f: TypeForm[Any] = list[int] | None

reveal_type(optional_arg(int | None))
reveal_type(injectable(dict, {}))

# a plain value must NOT be accepted where a type expression is expected
bad: TypeForm[Any] = 42
