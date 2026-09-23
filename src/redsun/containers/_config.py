"""The application container's configuration, as the container holds it."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, NotRequired

from redsun.virtual import RedSunConfig

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from .._config import Source
    from .components import _ComponentField as ComponentField

__all__ = ["AppConfig"]


class AppConfig(RedSunConfig, total=False):
    """Configuration of an application container.

    [`RedSunConfig`][redsun.virtual.RedSunConfig] plus the component sections,
    which the container reads and does not pass to components.
    """

    services: NotRequired[dict[str, Any]]
    devices: NotRequired[dict[str, Any]]
    presenters: NotRequired[dict[str, Any]]
    views: NotRequired[dict[str, Any]]
    storage: NotRequired[dict[str, Any] | None]
    wiring: NotRequired[list[dict[str, str]]]
    hooks: NotRequired[dict[str, dict[str, Any]]]


def refuse_unresolved_fields(
    owner: str, paths: Sequence[Source], fields: Mapping[str, ComponentField]
) -> None:
    """Refuse the container *owner* when a ``from_config`` field has no file.

    Checked at construction, not class creation, since a base class leaves
    ``config`` to its subclasses.

    Raises
    ------
    TypeError
        Naming every field wanting a configuration section.
    """
    if paths:
        return
    unresolved = sorted(
        attr_name
        for attr_name, field in fields.items()
        if field.from_config is not None
    )
    if unresolved:
        raise TypeError(
            f"Component field(s) {', '.join(unresolved)} in {owner} have "
            f"from_config set but no config path was provided to the container "
            f"class"
        )
