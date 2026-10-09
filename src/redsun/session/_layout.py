"""How the layout a session declares meets the placements its views ask for."""

from __future__ import annotations

from typing import TYPE_CHECKING, assert_never

from redsun.view import Column, Row, Tabs, WindowLayout

from ..view._layout import Split, names_in

if TYPE_CHECKING:
    from collections.abc import Collection, Mapping

    from redsun.view import Placement

    from ..view._layout import Node
    from ._frontend import Frontend

__all__ = ["resolved_layout"]


def resolved_layout(
    declared: WindowLayout | None,
    placements: Mapping[str, Placement | None],
    frontend: type[Frontend],
) -> tuple[WindowLayout, list[str]]:
    """Return the layout a window starts with, and the names of *declared* it drops.

    Every view *declared* names goes where it says. Every other view whose
    placement names a region joins it after what *declared* put there, as the
    frontend's `regions` say, the views of one group as tabs at the place of
    its first view. *placements* holds every view by name, in declaration
    order; `None` is a view whose placement is not known.

    A name no view placed in a region answers to is dropped, from the regions
    and from `hidden`.
    """
    declared = declared or WindowLayout()
    asked = {
        name: frontend.region_of(placement)
        for name, placement in placements.items()
        if placement is not None
    }
    in_region = {name for name, where in asked.items() if where is not None}
    named = set(declared.names)
    regions: dict[str, Node] = {}
    for region, node in declared.regions.items():
        kept = pruned(node, in_region)
        if kept is not None:
            regions[region] = kept
    joining: dict[str, list[str | tuple[str, str]]] = {}
    groups: dict[tuple[str, str], list[str]] = {}
    for name, where in asked.items():
        if where is None or name in named:
            continue
        region, group = where
        if group is None:
            joining.setdefault(region, []).append(name)
            continue
        if (region, group) not in groups:
            joining.setdefault(region, []).append((region, group))
        groups.setdefault((region, group), []).append(name)
    for region, items in joining.items():
        extras = [
            item if isinstance(item, str) else tabbed(groups[item]) for item in items
        ]
        regions[region] = joined(frontend.regions[region], regions.get(region), extras)
    placed = {name for node in regions.values() for name in names_in(node)}
    hidden = [name for name in declared.hidden if name in placed]
    dropped = [name for name in declared.names if name not in in_region]
    dropped += [
        name for name in declared.hidden if name not in placed and name not in dropped
    ]
    return WindowLayout(regions, declared.sizes, tuple(hidden)), dropped


def pruned(node: Node, keep: Collection[str]) -> Node | None:
    """Return *node* holding only the views in *keep*, `None` when none is left."""
    match node:
        case str():
            return node if node in keep else None
        case Tabs(names=names, current=current):
            kept = [name for name in names if name in keep]
            if not kept:
                return None
            return Tabs(*kept, current=current if current in kept else None)
        case Split(children=children, sizes=sizes):
            children_kept: list[Node] = []
            sizes_kept: list[float] = []
            for index, child in enumerate(children):
                kept_child = pruned(child, keep)
                if kept_child is not None:
                    children_kept.append(kept_child)
                    if sizes is not None:
                        sizes_kept.append(sizes[index])
            if not children_kept:
                return None
            kind = Row if isinstance(node, Row) else Column
            return kind(*children_kept, sizes=None if sizes is None else sizes_kept)
        case _:
            assert_never(node)


def tabbed(names: list[str]) -> Node:
    """Return the views of one group: tabs, or the view itself when it is alone."""
    return names[0] if len(names) == 1 else Tabs(*names)


def joined(
    kind: type[Row | Column | Tabs],
    declared: Node | None,
    extras: list[Node],
) -> Node:
    """Return what *declared* put in a region with *extras* joining it as *kind*."""
    if declared is None and len(extras) == 1:
        return extras[0]
    if issubclass(kind, Split):
        return kind(*([] if declared is None else [declared]), *extras)
    if isinstance(declared, Split):
        return Column(declared, joined(kind, None, extras))
    names = [
        name
        for node in [declared, *extras]
        if node is not None
        for name in names_in(node)
    ]
    current = declared.current if isinstance(declared, Tabs) else None
    return Tabs(*names, current=current)
