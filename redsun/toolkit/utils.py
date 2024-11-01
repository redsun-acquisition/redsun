from typing import TYPE_CHECKING

from psygnal import evented
from pydantic.dataclasses import dataclass

if TYPE_CHECKING:
	from typing import Any, Dict, Optional

__all__ = ["create_evented_dataclass"]


def create_evented_dataclass(
	cls_name: str,
	original_cls: type,
	types: "Optional[Dict[str, Any]]" = {},
	values: "Optional[Dict[str, Any]]" = {},
) -> type:
	""" Creates a new evented dataclass from the original provided one.\\
    For more information abount about evented dataclasses, see the `psygnal documentation <https://psygnal.readthedocs.io/en/latest/dataclasses/>`_.

    Parameters
    ----------
    cls_name : str
        Name of the new dataclass.
    original_cls : type
        Original dataclass.
    types : Optional[Dict[str, Any]]
        Dictionary of type annotations. Defaults to an empty dictionary.
    values : Optional[Dict[str, Any]]
        Dictionary of default values. Defaults to an empty dictionary.

    Returns
    -------
    type
        New evented dataclass.
    """

	# implementation provided by the following issue discussion:
	# https://github.com/pyapp-kit/psygnal/issues/328
	types = types or {}
	values = values or {}

	cls_dict = {
		"__annotations__": types,
	}
	cls_dict.update(values)
	cls = type(cls_name, (original_cls,), cls_dict)
	return evented(dataclass(cls, frozen=True))
