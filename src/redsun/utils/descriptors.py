"""Helper utilities for building bluesky-compatible descriptor and reading keys.

### Key format

Keys follow the convention:

```
    {name}-{property}
```

where:

- `name`` is the runtime device instance name;
- `property`` is the individual setting name.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, TypeVar, overload

if TYPE_CHECKING:
    from bluesky.protocols import Descriptor, Reading
    from event_model.documents import LimitsRange

__all__ = [
    "make_key",
    "parse_key",
    "make_descriptor",
    "make_reading",
]

T = TypeVar("T")


def make_key(name: str, property_name: str) -> str:
    """Build a canonical device property key.

    Parameters
    ----------
    name : str
        Runtime device instance name.
    property_name : str
        Individual setting name.

    Returns
    -------
    str
        Key in the form ``{name}-{property_name}``.
    """
    return f"{name}-{property_name}"


def parse_key(key: str) -> tuple[str, str]:
    """Parse a canonical device property key into its components.

    Parameters
    ----------
    key : str
        Key in the form ``{name}-{property_name}``.

    Returns
    -------
    tuple[str, str]
        ``(name, property_name)``

    Raises
    ------
    ValueError
        If the key does not conform to the expected format.
    """
    try:
        name, property_name = key.split("-", 1)
        return name, property_name
    except ValueError:
        raise ValueError(
            f"Key {key!r} does not conform to the expected "
            f"'{{name}}-{{property}}' format."
        )


@overload
def make_descriptor(
    source: str,
    dtype: Literal["number"],
    *,
    low: float | None = ...,
    high: float | None = ...,
    units: str | None = ...,
    readonly: bool = ...,
) -> Descriptor: ...
@overload
def make_descriptor(
    source: str,
    dtype: Literal["integer"],
    *,
    low: int | None = ...,
    high: int | None = ...,
    units: str | None = ...,
    readonly: bool = ...,
) -> Descriptor: ...
@overload
def make_descriptor(
    source: str,
    dtype: Literal["string"],
    *,
    choices: list[str] | None = ...,
    units: str | None = ...,
    readonly: bool = ...,
) -> Descriptor: ...
@overload
def make_descriptor(
    source: str,
    dtype: Literal["array"],
    *,
    shape: list[int | None] = ...,
    units: str | None = ...,
    readonly: bool = ...,
) -> Descriptor: ...
@overload
def make_descriptor(
    source: str,
    dtype: Literal["boolean"],
    *,
    readonly: bool = ...,
) -> Descriptor: ...
def make_descriptor(
    source: str,
    dtype: Literal["number", "integer", "string", "array", "boolean"],
    *,
    low: float | int | None = None,
    high: float | int | None = None,
    units: str | None = None,
    choices: list[str] | None = None,
    shape: list[int | None] | None = None,
    readonly: bool = False,
) -> Descriptor:
    """Build a bluesky-compatible descriptor entry.

    Parameters
    ----------
    source : str
        Human-readable source label (e.g. `"settings"`).
    dtype : Literal["number", "integer", "string", "array", "boolean"]
        Data type of the field.
    low : float | int | None
        Lower control limit (`"number"`` or `"integer"` only).
    high : float | int | None
        Upper control limit (`"number"`` or `"integer"` only).
    units : str | None
        Physical unit string.
    choices : list[str] | None
        Allowed string values (`"string"` only).
    shape : list[int | None] | None
        Array dimensions (required for `"array"`).
    readonly : bool
        When ``True``, the ``source`` field is suffixed with `":readonly"`.

    Returns
    -------
    Descriptor
        The constructed descriptor dictionary.
    """
    source_field = f"{source}:readonly" if readonly else source
    d: Descriptor = {"source": source_field, "dtype": dtype, "shape": []}
    if units is not None:
        d["units"] = units

    match dtype:
        case "number" | "integer":
            if low is not None and high is not None:
                limits: LimitsRange = {"low": float(low), "high": float(high)}
                d["limits"] = {"control": limits}
            if units is not None:
                d["units"] = units
        case "string":
            if choices is not None:
                d["choices"] = choices
        case "array":
            if shape is None:
                raise ValueError("'shape' is required when dtype='array'.")
            d["shape"] = shape
        case _:
            ...  # nothing to do
    return d


def make_reading(value: T, timestamp: float) -> Reading[T]:
    """Build a bluesky-compatible reading entry.

    Parameters
    ----------
    value : T
        Current value for the property.
    timestamp : float
        UNIX timestamp of the reading
        (i.e. return value of `time.time()`).

    Returns
    -------
    Reading[T]
    """
    return {"value": value, "timestamp": timestamp}


def parse_map_key(input: str, map_prefix: str) -> tuple[str, str, str]:
    """Split a descriptor or reading key coming from a [`DeviceMap`][redsun.device.DeviceMap] into its components.

    Parameters
    ----------
    input : str
        The input key to parse, expected to be in the form ``{name}-{map_prefix}-{key}``.
    map_prefix : str
        The prefix used in the key to identify the map (e.g. "axis").

    Returns
    -------
    tuple[str, str, str]
        A tuple of the form ``(name, map_key, key)``, where:
        - `name` is the device name (the part before the first hyphen).
        - `map_key` is the key identifying the map (the part between the first and second hyphens).
        - `key` is the specific property key (the part after the second hyphen).
    """
    ret = input.split("-", 2)
    if len(ret) != 3 or ret[1] != map_prefix:
        raise ValueError(
            f"Input {input!r} does not conform to the expected "
            f"'{{name}}-{map_prefix}-{{key}}' format."
        )
    return ret[0], ret[1], ret[2]
