from psygnal import evented
from pydantic.dataclasses import dataclass

__all__ = ['create_evented_dataclass']

def create_evented_dataclass(cls_name: str, 
                              original_cls : type,
                              types : dict = {},
                              values : dict = {}) -> type:
    """ Creates a new evented dataclass from the original provided one.\\
    For more information abount about evented dataclasses, see the `psygnal documentation <https://psygnal.readthedocs.io/en/latest/dataclasses/>`_.

    Parameters
    ----------
    cls_name : str
        Name of the new dataclass.
    original_cls : type
        Original dataclass.
    types : dict
        Dictionary of type annotations.
    values : dict
        Dictionary of default values.

    Returns
    -------
    type
        New evented dataclass.
    """

    # implementation provided by the following issue discussion:
    # https://github.com/pyapp-kit/psygnal/issues/328

    cls_dict = {
        "__annotations__": types,
    }
    cls_dict.update(values)
    cls = type(cls_name, (original_cls), cls_dict)
    return evented(dataclass(cls, frozen=True))