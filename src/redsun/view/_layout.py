"""Where a session's views start in its window, region by region."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, assert_never

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping, Sequence
    from typing import TypeAlias

__all__ = ["Column", "Row", "Tabs", "WindowLayout"]


def split_problems(count: int, sizes: Sequence[float] | None) -> list[str]:
    """Return what is wrong with a row or column of *count* children weighted by *sizes*."""
    problems = []
    if count == 0:
        problems.append("holds nothing")
    if sizes is not None:
        if len(sizes) != count:
            problems.append(f"has {count} children but {len(sizes)} sizes")
        if any(size <= 0 for size in sizes):
            problems.append(f"has sizes {list(sizes)}, one of them not positive")
    return problems


def tabs_problems(names: Sequence[str], current: str | None) -> list[str]:
    """Return what is wrong with tabs of *names* showing *current* on top."""
    problems = []
    if not names:
        problems.append("holds nothing")
    if current is not None and current not in names:
        problems.append(f"shows {current!r} on top, which is not one of its tabs")
    return problems


@dataclass(frozen=True)
class Split:
    """Views sharing a space in one direction, each child taking a share of it."""

    children: tuple[Node, ...]
    """What shares the space, in order."""

    sizes: tuple[float, ...] | None = None
    """One positive weight per child, or `None` for equal shares."""

    def __post_init__(self) -> None:
        problems = split_problems(len(self.children), self.sizes)
        if problems:
            raise ValueError(f"{type(self).__name__} {'; '.join(problems)}")


class Row(Split):
    """Views side by side, left to right.

    Each child is a view's name or another node. `sizes` gives one positive
    weight per child, and each child takes its weight's share of the width;
    without it the children share the width equally.

    Raises
    ------
    ValueError
        If it holds nothing, or *sizes* does not give one positive weight per
        child.
    """

    def __init__(self, *children: Node, sizes: Sequence[float] | None = None) -> None:
        super().__init__(children, None if sizes is None else tuple(sizes))


class Column(Split):
    """Views stacked, top to bottom.

    Each child is a view's name or another node. `sizes` gives one positive
    weight per child, and each child takes its weight's share of the height;
    without it the children share the height equally.

    Raises
    ------
    ValueError
        If it holds nothing, or *sizes* does not give one positive weight per
        child.
    """

    def __init__(self, *children: Node, sizes: Sequence[float] | None = None) -> None:
        super().__init__(children, None if sizes is None else tuple(sizes))


@dataclass(frozen=True)
class TabGroup:
    """Views sharing one space as tabs."""

    names: tuple[str, ...]
    """The views, in the order of their tabs."""

    current: str | None = None
    """The view shown on top, or `None` for the first."""

    def __post_init__(self) -> None:
        problems = tabs_problems(self.names, self.current)
        if problems:
            raise ValueError(f"Tabs {'; '.join(problems)}")


class Tabs(TabGroup):
    """Views sharing one space as tabs.

    Each tab is a view's name. `current` names the view shown on top; without
    it the first is.

    Raises
    ------
    ValueError
        If it holds nothing, or *current* is not one of its tabs.
    """

    def __init__(self, *names: str, current: str | None = None) -> None:
        super().__init__(names, current)


Node: TypeAlias = str | Split | Tabs
"""A view's name, or views arranged together."""


def names_in(node: Node) -> Iterator[str]:
    """Yield the name of every view in *node*, in order."""
    match node:
        case str():
            yield node
        case Tabs(names=names):
            yield from names
        case Split(children=children):
            for child in children:
                yield from names_in(child)
        case _:
            assert_never(node)


def written(node: Node) -> str | dict[str, object]:
    """Return *node* as a session file writes it."""
    match node:
        case str():
            return node
        case Tabs(names=names, current=current):
            tabs: dict[str, object] = {"tabs": list(names)}
            if current is not None:
                tabs["current"] = current
            return tabs
        case Split(children=children, sizes=sizes):
            key = "row" if isinstance(node, Row) else "column"
            split: dict[str, object] = {key: [written(child) for child in children]}
            if sizes is not None:
                split["sizes"] = list(sizes)
            return split
        case _:
            assert_never(node)


def layout_problems(
    regions: Mapping[str, Node], sizes: Mapping[str, float]
) -> list[str]:
    """Return what is wrong with a layout filling *regions* and giving them *sizes*."""
    problems = []
    counts = Counter(name for node in regions.values() for name in names_in(node))
    twice = sorted(name for name, count in counts.items() if count > 1)
    if twice:
        problems.append(f"places {', '.join(map(repr, twice))} more than once")
    for region, share in sizes.items():
        if not 0 < share < 1:
            problems.append(
                f"gives region {region!r} a share of {share}; a share lies "
                "between 0 and 1"
            )
    return problems


@dataclass(frozen=True)
class WindowLayout:
    """Where views start in a window: what fills each region, how big it is, what starts hidden.

    The region names are the frontend's. A view the layout leaves out goes
    where its own placement asks.

    Raises
    ------
    ValueError
        Listing every problem: a view placed twice, or a share outside
        (0, 1).
    """

    regions: Mapping[str, Node] = field(default_factory=dict)
    """What fills each region, by region name."""

    sizes: Mapping[str, float] = field(default_factory=dict)
    """The share of the window each region takes, between 0 and 1, by region name."""

    hidden: Sequence[str] = ()
    """The views that start hidden."""

    def __post_init__(self) -> None:
        problems = layout_problems(self.regions, self.sizes)
        if problems:
            raise ValueError(f"WindowLayout {'; '.join(problems)}")

    @property
    def names(self) -> list[str]:
        """The name of every view the layout places, region by region."""
        return [name for node in self.regions.values() for name in names_in(node)]

    def fingerprint(self) -> str:
        """Return a digest that changes whenever the layout does."""
        content = {
            "regions": {region: written(node) for region, node in self.regions.items()},
            "sizes": dict(self.sizes),
            "hidden": sorted(self.hidden),
        }
        return hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()
