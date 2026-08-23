# ruff: noqa
"""Build stages, as dishka scopes."""

from __future__ import annotations

from dishka import BaseScope, new_scope


class AppScope(BaseScope):
    """The stages a redsun application is built in.

    A dependency declared at a later stage cannot be reached from an earlier
    one, which is how "this needs every component to exist" is expressed
    without a lifecycle hook.
    """

    RUNTIME = new_scope("RUNTIME")
    COMPONENT = new_scope("COMPONENT")
    WIRED = new_scope("WIRED")


_ORDER = (AppScope.RUNTIME, AppScope.COMPONENT, AppScope.WIRED)


def latest(*scopes: AppScope) -> AppScope:
    """The last of *scopes* in build order."""
    return max(scopes, key=_ORDER.index)


__all__ = ["AppScope", "latest"]
