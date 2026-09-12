"""Configuration sources, and the rules for laying one over another.

Lives at the package root because `redsun.containers` and `redsun.experimental`
both need it and neither may import the other's private modules.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeAlias

import yaml

if TYPE_CHECKING:
    from collections.abc import Collection, Sequence

Source: TypeAlias = str | Path | Mapping[str, Any]
"""One configuration source: a path to a YAML file, or a mapping in hand."""

logger = logging.getLogger("redsun")

__all__ = [
    "COMPONENT_SECTIONS",
    "IDENTITY_KEYS",
    "Source",
    "as_sources",
    "label",
    "load",
    "merge_config",
    "read",
    "refuse_identity_conflict",
]

COMPONENT_SECTIONS: frozenset[str] = frozenset({"devices", "presenters", "views"})
"""The configuration sections whose entries are a component's constructor call."""

IDENTITY_KEYS: tuple[str, ...] = ("schema_version", "frontend")
"""Keys naming what kind of session this is, which every layered source must agree on.

Everything else describes the session's content, where a later source
legitimately overrides an earlier one. ``name`` is content by this rule: a
caller laying ``{"name": "run-2"}`` over a shared file is renaming that
session, not contradicting it.
"""


def as_sources(declared: Source | Sequence[Source] | None) -> list[Source]:
    """Return *declared* as the sequence of sources it stands for.

    One source is a sequence of one. A string is a path rather than the
    sequence of characters it also is, and a mapping is a source rather than a
    sequence of its keys.
    """
    if declared is None:
        return []
    if isinstance(declared, (str, Path, Mapping)):
        return [declared]
    return list(declared)


def read(source: Source) -> dict[str, Any]:
    """Read one configuration source into a mapping.

    A string or a path names a YAML file; a mapping is already the answer and
    is copied so that laying another source over it cannot reach the caller's.

    Raises
    ------
    TypeError
        If the file's top level is not a mapping.
    """
    if not isinstance(source, (str, Path)):
        return dict(source)
    with open(source) as fh:
        data = yaml.safe_load(fh)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise TypeError(
            f"Expected a YAML mapping at top level in {source}, got "
            f"{type(data).__name__}"
        )
    return data


def label(source: Source) -> str:
    """Name *source* as an error message should refer to it."""
    if isinstance(source, (str, Path)):
        return str(source)
    return "an inline mapping"


def merge_config(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Return *base* with *overlay* laid over it, merging nested mappings.

    A key present in both is taken from *overlay* unless both values are
    mappings, which merge in turn. Anything that is not a mapping - a list, a
    scalar - is replaced rather than combined.

    A component entry is the exception: under ``devices``, ``presenters`` and
    ``views`` the section merges by component name, but a component *named* in
    *overlay* is taken from it whole. Those entries are the keyword arguments
    of a constructor call rather than a tree of settings, so one source owns
    one component's arguments and a reader stops at the last source naming it.
    """
    merged = dict(base)
    for key, value in overlay.items():
        current = merged.get(key)
        if not (isinstance(current, dict) and isinstance(value, dict)):
            merged[key] = value
        elif key in COMPONENT_SECTIONS:
            for shadowed in current.keys() & value.keys():
                logger.debug(
                    f"Component '{shadowed}' in '{key}' is taken from a later "
                    f"configuration source, replacing the entry under it"
                )
            merged[key] = {**current, **value}
        else:
            merged[key] = merge_config(current, value)
    return merged


def refuse_identity_conflict(
    data: Mapping[str, Any], overlay: Mapping[str, Any], source: Source
) -> None:
    """Refuse a source that contradicts what an earlier one said the session is.

    Raises
    ------
    ValueError
        If *overlay* gives a different value for a key naming the session's
        identity rather than its content.
    """
    for key in IDENTITY_KEYS:
        if key in data and key in overlay and data[key] != overlay[key]:
            raise ValueError(
                f"Configuration source {label(source)} sets {key}={overlay[key]!r}, "
                f"which contradicts {data[key]!r} from a source layered under it. "
                f"{key} names what kind of session this is, so every source must "
                f"agree on it."
            )


def load(
    declared: Source | Sequence[Source] | None,
    required: Collection[str] = frozenset(),
) -> dict[str, Any]:
    """Read what *declared* names in order, laying each over the last.

    One source or several, so a caller with a single file hands it over as it
    is. *required* is checked against the merged mapping rather than against
    each source, so a source layered under another may carry a fragment.

    Raises
    ------
    ValueError
        If two sources disagree about the session's identity.
    KeyError
        If the merged mapping is missing a required key.
    """
    ordered = as_sources(declared)
    if len(ordered) > 1:
        logger.debug(
            f"Reading configuration from {len(ordered)} sources, in order: "
            f"{', '.join(label(source) for source in ordered)}"
        )
    data: dict[str, Any] = {}
    for source in ordered:
        overlay = read(source)
        refuse_identity_conflict(data, overlay, source)
        data = merge_config(data, overlay)
    missing = set(required) - data.keys()
    if missing:
        named = ", ".join(label(source) for source in ordered) or "no sources"
        raise KeyError(
            f"Configuration ({named}) is missing required keys: "
            f"{', '.join(sorted(missing))}"
        )
    return data
