from psygnal import evented
from pydantic.dataclasses import dataclass

def create_evented_model_info(cls_name: str, 
                              original_cls : type,
                              type_dict : dict,
                              value_dict : dict) -> type:
    """ Creates a new evented dataclass from the original dataclass.\\
    Each model will create a new evented dataclass which is subclassed from the original model RedSun provides,\\
    allowing to add new properties that can be exposed to the upper layers using `psygnal`.\\
    For more information abount about evented dataclasses, see the `psygnal documentation <https://psygnal.readthedocs.io/en/latest/dataclasses/>`_.

    Parameters
    ----------
    cls_name : str
        Name of the new dataclass.
    original_cls : type
        Original dataclass.
    type_dict : dict
        Dictionary of type annotations.
    value_dict : dict
        Dictionary of default values.

    Returns
    -------
    type
        New evented dataclass.
    """

    # implementation provided by the following issue discussion:
    # https://github.com/pyapp-kit/psygnal/issues/328

    cls_dict = {
        "__annotations__": type_dict,
    }
    cls_dict.update(value_dict)
    cls = type(cls_name, (original_cls), cls_dict)
    return evented(dataclass(cls, frozen=True))