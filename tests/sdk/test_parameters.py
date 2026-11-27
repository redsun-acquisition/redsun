"""Tests for sorting a constructor's parameters for describing."""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Annotated, Any, Literal, Protocol

import pytest
from annotated_types import Gt
from pydantic import BaseModel, Field

from redsun import DeviceMapping, DevicesOf, SessionConfig
from redsun.compute import ThreadExecutor
from redsun.session._base import HELD
from redsun.session._factories import parameters_of

if TYPE_CHECKING:
    from decimal import Decimal as Unavailable


class Movable(Protocol):
    """Anything that moves."""

    def set(self, value: float) -> None:
        """Move to *value*."""


class Calibration(BaseModel):
    """A value a provider could share."""

    offset: float


class Other:
    """A class with no JSON Schema."""


class Sorted:
    """A presenter asking for one parameter of each kind."""

    def __init__(
        self,
        name: str,
        *,
        step: Annotated[float, Gt(0), Field(title="Step")] = 1.0,
        mode: Literal["fast", "fine"] = "fine",
        calibration: Calibration,
        devices: DeviceMapping,
        config: SessionConfig,
        motors: DevicesOf[Movable],
        pool: ThreadExecutor,
        other: Other,
    ) -> None:
        self.name = name


class Gappy:
    """A presenter naming a type that exists only for a type checker."""

    def __init__(self, name: str, *, gone: Unavailable, step: float = 1.0) -> None:
        self.name = name


class Free:
    """A presenter with a parameter that carries no annotation."""

    def __init__(self, name: str, x) -> None:  # type: ignore[no-untyped-def]
        self.name = name


class Open:
    """A presenter taking any keyword."""

    def __init__(self, name: str, **kwargs: Any) -> None:
        self.name = name


@dataclasses.dataclass
class Fields:
    """A presenter written as a dataclass."""

    name: str
    step: float = 1.0


def test_each_parameter_is_sorted() -> None:
    """Sort file keys, session-filled parameters and model types as the spec says."""
    found = parameters_of(Sorted, HELD)

    assert set(found.fields) == {"step", "mode", "calibration"}
    assert found.fields["mode"][1] == "fine"
    assert found.fields["calibration"][1] is ...
    filled = {f.name: f for f in found.filled}
    assert set(filled) == {
        "calibration",
        "devices",
        "config",
        "motors",
        "pool",
        "other",
    }
    assert filled["calibration"].file and filled["calibration"].required
    assert filled["devices"].type == "redsun.DeviceMapping"
    assert not filled["devices"].file
    assert found.problems == {}
    assert found.refusal is None
    assert not found.open


def test_a_name_missing_at_runtime_is_a_problem_of_its_key() -> None:
    """Report the key naming a missing type, refuse the class, and sort the rest."""
    found = parameters_of(Gappy, HELD)

    assert "Unavailable" in found.problems["gone"]
    assert "step" in found.fields
    assert found.refusal is not None and "Unavailable" in found.refusal


@pytest.mark.parametrize("default", [True, False], ids=["default", "no-default"])
def test_a_positional_only_parameter_is_a_problem(default: bool) -> None:
    """Report a positional-only parameter, and refuse the class when it has no default."""
    if default:

        class Positional:
            def __init__(self, scale: float = 1.0, /, name: str = "") -> None:
                self.name = name

    else:

        class Positional:  # type: ignore[no-redef]
            def __init__(self, scale: float, /, name: str = "") -> None:
                self.name = name

    found = parameters_of(Positional, HELD)

    assert "scale" in found.problems
    assert (found.refusal is None) is default


def test_a_parameter_without_annotation_is_a_free_field() -> None:
    """Describe an unannotated parameter as any value, and report it."""
    found = parameters_of(Free, HELD)

    assert found.fields["x"] == (Any, ...)
    assert "x" in found.problems


def test_kwargs_opens_the_entry() -> None:
    """Mark a class taking `**kwargs` as accepting any key."""
    assert parameters_of(Open, HELD).open


def test_a_dataclass_component_is_sorted_by_its_fields() -> None:
    """Read a dataclass's fields as its constructor's parameters."""
    assert parameters_of(Fields, HELD).fields == {"step": (float, 1.0)}
