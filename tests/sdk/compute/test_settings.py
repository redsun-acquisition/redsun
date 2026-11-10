"""Tests for the compute section of a session."""

from __future__ import annotations

from types import UnionType
from typing import (
    TYPE_CHECKING,
    Any,
    Union,
    get_args,
    get_origin,
    get_type_hints,
    is_typeddict,
)

import pytest
from pydantic import ValidationError

from redsun._config import ComputeConfig
from redsun.compute import ComputeSettings, Preset

if TYPE_CHECKING:
    from pydantic import BaseModel


def without_none(annotation: Any) -> Any:
    """Return *annotation* with `None` taken out of a union."""
    if get_origin(annotation) not in (Union, UnionType):
        return annotation
    rest = tuple(a for a in get_args(annotation) if a is not type(None))
    return rest[0] if len(rest) == 1 else annotation


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
        if is_typeddict(found):
            differences += [f"{key}.{line}" for line in mirrored(found, expected)]  # type: ignore[arg-type]
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
    assert ComputeConfig.model_validate("latency").preset == "latency"


def test_an_unknown_key_is_refused() -> None:
    """Refuse a misspelt key in the compute section."""
    with pytest.raises(ValidationError):
        ComputeConfig.model_validate({"preest": "latency"})
