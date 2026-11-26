"""An example session holding every built-in component, over simulated devices."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ._app import ExampleApp

__all__ = ["ExampleApp", "example_config"]


def example_config(style: str | None) -> dict[str, Any]:
    """Return the configuration showing the example in *style*, or in the platform's look for `None`.

    *style* is the short name of a style `redsun` ships, as a session file
    writes it.
    """
    if style is None:
        return {}
    return {"hooks": {"configure_application": style}}


def __getattr__(name: str) -> object:
    """Load `ExampleApp` on first use, so the package imports without a Qt binding."""
    if name == "ExampleApp":
        from ._app import ExampleApp  # noqa: PLC0415

        return ExampleApp
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
