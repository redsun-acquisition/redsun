"""Tests for sorting a constructor's parameters for describing."""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from typing import TYPE_CHECKING, Annotated, Any, Literal, NewType, Protocol, TypeVar

import pytest
from annotated_types import Gt
from ophyd_async.core import PathProvider
from pydantic import BaseModel, Field

from redsun import DeviceMapping, DevicesOf, SessionConfig
from redsun.compute import ThreadExecutor
from redsun.session._base import HELD
from redsun.session._factories import parameters_of

if TYPE_CHECKING:
    from decimal import Decimal as Unavailable

Gain = NewType("Gain", float)
"""A value a provider could share, named by its own type."""

Later = NewType("Later", "Offset")
"""A `NewType` whose supertype is a name `pydantic` cannot resolve."""

Bound = TypeVar("Bound", bound="Other")
"""A type variable whose bound is a name `pydantic` cannot resolve."""


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


class Offset(float):
    """The supertype `Later` names."""


class Unwritable:
    """A presenter with keys whose schema `pydantic` fails to write."""

    def __init__(
        self,
        name: str,
        *,
        later: Later,
        kind: type[Bound] = Other,  # type: ignore[assignment]
        step: float = 1.0,
    ) -> None:
        self.name = name


class Detector:
    """A device asking for one parameter of each kind a device can take."""

    def __init__(
        self,
        prefix: str,
        path_provider: PathProvider,
        calibration: Calibration,
        generator: Other | None,
        sigs: Sequence[Other] = (),
        name: str = "",
    ) -> None:
        self.name = name


class Mapped:
    """A device asking for something no session file can give."""

    def __init__(self, prefix: str, devices: DeviceMapping, name: str = "") -> None:
        self.name = name


class Labelled:
    """A component taking an optional value without a default."""

    def __init__(self, name: str, *, label: str | None) -> None:
        self.name = name


class Suffixed:
    """A component with an unannotated parameter that has a default."""

    def __init__(self, name: str, suffix="cam1:") -> None:  # type: ignore[no-untyped-def]
        self.name = name


class Typed:
    """A presenter whose session-filled parameters print as types."""

    def __init__(
        self,
        name: str,
        *,
        motors: DevicesOf[Movable],
        pool: ThreadExecutor,
        gain: Gain,
        other: Other | None,
        others: Sequence[Other],
        devices: DeviceMapping,
    ) -> None:
        self.name = name


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


def test_a_schema_pydantic_cannot_write_is_a_problem_of_its_key() -> None:
    """Report a key whose schema `pydantic` fails to write, take any value for it, and sort the rest."""
    found = parameters_of(Unwritable, HELD)

    assert set(found.problems) == {"later", "kind"}
    assert "ForwardRef" in found.problems["kind"]
    assert "errors.pydantic.dev" not in found.problems["later"]
    assert found.fields["later"] == (Any, ...)
    assert found.fields["kind"] == (Any, Other)
    assert found.fields["step"] == (float, 1.0)
    assert [(f.name, f.file) for f in found.filled] == [("later", True)]
    assert found.refusal is None


def test_a_device_is_given_nothing_by_type() -> None:
    """Fill only a device's `path_provider`, by name, and take every other key from the file."""
    found = parameters_of(Detector, HELD, device=True)

    assert found.fields == {
        "prefix": (str, ...),
        "calibration": (Calibration, ...),
        "generator": (None, ...),
    }
    assert [(f.name, f.type, f.file) for f in found.filled] == [
        ("path_provider", "ophyd_async.core.PathProvider", False)
    ]
    assert found.problems == {}
    assert found.refusal is None


def test_a_device_asking_for_what_no_file_gives_is_refused() -> None:
    """Refuse a device with a required parameter that has no schema."""
    found = parameters_of(Mapped, HELD, device=True)

    assert found.refusal is not None and "'devices'" in found.refusal


@pytest.mark.parametrize(("device", "default"), [(False, None), (True, ...)])
def test_an_optional_value_without_a_default_defaults_to_none(
    device: bool, default: object
) -> None:
    """Default `X | None` to `None` for a presenter or view, and keep it required for a device."""
    found = parameters_of(Labelled, HELD, device=device)

    assert found.fields["label"] == (str | None, default)


@pytest.mark.parametrize(
    ("device", "field", "problem"),
    [(False, (Any, ...), True), (True, (Any, "cam1:"), False)],
)
def test_an_unannotated_parameter_with_a_default(
    device: bool, field: tuple[object, object], problem: bool
) -> None:
    """Require an unannotated key of a presenter or view and report it; keep a device's default."""
    found = parameters_of(Suffixed, HELD, device=device)

    assert found.fields["suffix"] == field
    assert ("suffix" in found.problems) is problem


def test_a_type_prints_as_a_python_expression() -> None:
    """Print each session-filled type with its names under their public packages."""
    found = parameters_of(Typed, HELD)

    assert {f.name: f.type for f in found.filled} == {
        "motors": f"redsun.DevicesOf[{__name__}.Movable]",
        "pool": "redsun.compute.ThreadExecutor",
        "gain": f"{__name__}.Gain",
        "other": f"{__name__}.Other | None",
        "others": f"Sequence[{__name__}.Other]",
        "devices": "redsun.DeviceMapping",
    }
