"""Tests for the compute section of a session."""

from __future__ import annotations

from types import UnionType
from typing import (
    TYPE_CHECKING,
    Annotated,
    Any,
    Union,
    get_args,
    get_origin,
    get_type_hints,
    is_typeddict,
)

import pytest
from pydantic import ValidationError

from redsun._config import ComputeConfig, load
from redsun.compute import ComputeSettings, Preset

if TYPE_CHECKING:
    from pathlib import Path

    from pydantic import BaseModel


def without_none(annotation: Any) -> Any:
    """Return *annotation* with `None` taken out of a union."""
    if get_origin(annotation) not in (Union, UnionType):
        return annotation
    rest = tuple(a for a in get_args(annotation) if a is not type(None))
    return rest[0] if len(rest) == 1 else annotation


def without_limits(annotation: Any) -> Any:
    """Return *annotation* with the limits a model puts on a type taken off."""
    origin, args = get_origin(annotation), get_args(annotation)
    if origin is Annotated:
        return without_limits(args[0])
    if origin is list:
        return list[without_limits(args[0])]  # type: ignore[misc]
    return annotation


def mirrored(typed: type, model: type[BaseModel]) -> list[str]:
    """Return one line per way *typed* and *model* differ, key by key and type by type."""
    keys = get_type_hints(typed, localns={"Preset": Preset})
    fields = model.model_fields
    differences = [
        f"{key}: only in the TypedDict" for key in keys.keys() - fields.keys()
    ]
    differences += [f"{key}: only in the model" for key in fields.keys() - keys.keys()]
    for key in keys.keys() & fields.keys():
        field, found = fields[key], keys[key]
        expected = field.annotation
        if field.default is None:
            expected = without_none(expected)
            found = without_none(found)
        expected = without_limits(expected)
        if is_typeddict(found):
            differences += [f"{key}.{line}" for line in mirrored(found, expected)]
        elif found != expected:
            differences.append(
                f"{key}: {found} in the TypedDict, {expected} in the model"
            )
    return differences


def test_the_typed_dict_mirrors_the_model() -> None:
    """Keep ComputeSettings and ComputeConfig in step, key by key and type by type."""
    assert mirrored(ComputeSettings, ComputeConfig) == []


def test_a_preset_word_is_a_section() -> None:
    """Read a bare preset as a compute section naming it."""
    assert load([{"compute": "latency"}]) == {"compute": {"preset": "latency"}}


def test_an_unknown_key_is_refused() -> None:
    """Refuse a misspelt key in the compute section."""
    with pytest.raises(ValidationError):
        ComputeConfig.model_validate({"preest": "latency"})


@pytest.mark.parametrize(
    "section",
    [
        {"cores": 0},
        {"reserve": -1},
        {"switch_interval_ms": 0},
        {"switch_interval_ms": -1.5},
    ],
)
def test_a_value_out_of_range_is_refused(section: dict[str, Any]) -> None:
    """Refuse a core count, a reserve or an interval that cannot be right."""
    with pytest.raises(ValidationError):
        ComputeConfig.model_validate(section)


def test_a_preset_word_in_a_file_keeps_the_keys_under_it(tmp_path: Path) -> None:
    """Merge a file's bare preset with the class's keys instead of replacing them."""
    path = tmp_path / "session.yaml"
    path.write_text("compute: latency\n", encoding="utf-8")

    assert load([{"compute": {"cores": 4}}, path]) == {
        "compute": {"preset": "latency", "cores": 4}
    }
