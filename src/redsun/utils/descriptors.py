"""Helpers parsing `bluesky` descriptor and reading keys.

### Key format

Keys follow the `ophyd-async` child naming convention:

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
    """Split a key of the form `{name}-{property_name}` into `(name, property_name)`.

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
        ) from None


def parse_map_key(key: str, map_prefix: str) -> tuple[str, str, str]:
    """Split a descriptor or reading key of a [`DeviceMap`][ophyd_async.core.DeviceMap] into its parts.

    Returns `(name, map_key, key)`: the device name (before the first hyphen),
    the map key (between the first and second hyphens) and the property key
    (after the second hyphen).

    Parameters
    ----------
    key
        The key to parse, expected to be in the form `{name}-{map_prefix}-{key}`.
    map_prefix
        The prefix used in the key to identify the map (e.g. "axis").

    Raises
    ------
    ValueError
        If *key* has fewer than three parts, or its second part is not
        *map_prefix*.
    """
    parts = key.split("-", 2)
    if len(parts) != 3 or parts[1] != map_prefix:
        raise ValueError(
            f"Input {key!r} does not conform to the expected "
            f"'{{name}}-{map_prefix}-{{key}}' format."
        )
    return parts[0], parts[1], parts[2]
