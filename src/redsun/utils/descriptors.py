"""Helpers parsing ``bluesky`` descriptor and reading keys.

### Key format

Keys follow the ``ophyd-async`` child naming convention:

```
    {name}-{property}
```

where:

- `name` is the runtime device instance name;
- `property` is the individual setting name.
"""

from __future__ import annotations

__all__ = [
    "parse_key",
    "parse_map_key",
]


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


def parse_map_key(input: str, map_prefix: str) -> tuple[str, str, str]:
    """Split a descriptor or reading key of a [`DeviceMap`][ophyd_async.core.DeviceMap] into its parts.

    Parameters
    ----------
    input : str
        The input key to parse, expected to be in the form ``{name}-{map_prefix}-{key}``.
    map_prefix : str
        The prefix used in the key to identify the map (e.g. "axis").

    Returns
    -------
    tuple[str, str, str]
        ``(name, map_key, key)``: the device name (before the first hyphen),
        the map key (between the first and second hyphens) and the property
        key (after the second hyphen).
    """
    ret = input.split("-", 2)
    if len(ret) != 3 or ret[1] != map_prefix:
        raise ValueError(
            f"Input {input!r} does not conform to the expected "
            f"'{{name}}-{map_prefix}-{{key}}' format."
        )
    return ret[0], ret[1], ret[2]
