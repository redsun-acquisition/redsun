"""The ``actions`` configuration section, read into the actions it declares."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from app_model.types import Action

__all__ = ["ActionError", "action_from_entry", "read_actions"]


class ActionError(RuntimeError):
    """An ``actions`` configuration entry cannot be turned into an action."""


def read_actions(raw: object, owner: str) -> list[Action[..., Any]]:
    """Read the ``actions`` section of *owner*'s configuration, one per entry.

    Parameters
    ----------
    raw : object
        The section as the configuration carried it, which need not be a list.
    owner : str
        How to name the configuration in a refusal, usually the session's own
        name.

    Reading imports nothing a session did not already import: a ``callback``
    stays the ``module:function`` string it was written as, and app-model
    imports it when the command first runs.

    Raises
    ------
    ActionError
        If the section is not a list, or an entry is not an action.
    """
    if raw is None:
        return []
    if isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence):
        raise ActionError(
            f"actions section of {owner} must be a list of entries, got "
            f"{type(raw).__name__}"
        )
    return [action_from_entry(entry, position) for position, entry in enumerate(raw)]


def action_from_entry(entry: object, position: int) -> Action[..., Any]:
    """Read one ``actions`` entry, named by its id or by where it appears.

    Raises
    ------
    ActionError
        If the entry is not a mapping, carries a key an action does not take,
        or leaves out one it requires.
    """
    if not isinstance(entry, Mapping):
        raise ActionError(
            f"actions entry at position {position} must be a mapping, got "
            f"{type(entry).__name__}"
        )
    fields: dict[str, Any] = {str(key): value for key, value in entry.items()}
    declared = fields.get("id")
    named = repr(declared) if isinstance(declared, str) else f"at position {position}"
    unknown = sorted(key for key in fields if key not in Action.model_fields)
    if unknown:
        raise ActionError(
            f"actions entry {named} carries unknown key(s) {', '.join(unknown)}; "
            f"an entry takes the fields of an action, which are "
            f"{', '.join(sorted(Action.model_fields))}"
        )
    try:
        return Action(**fields)
    except ValueError as e:
        raise ActionError(f"actions entry {named} is not an action: {e}") from e
