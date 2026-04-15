"""Factory for constructing :class:`SharedDetectorWriter` instances by MIME type."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from redsun.storage import SharedDetectorWriter


def create_writer(
    name: str,
    mimetype: str = "application/x-zarr",
    **kwargs: Any,
) -> SharedDetectorWriter:
    """Construct a :class:`SharedDetectorWriter` for the given MIME type.

    The concrete backend class is selected by matching *mimetype* against
    each registered writer's
    [`_class_mimetype()`][redsun.storage.SharedDetectorWriter._class_mimetype].
    The backend import is deferred until the factory is called, so the private
    implementation modules never appear at the call site.

    Parameters
    ----------
    name :
        Store group name forwarded to the writer constructor.
    mimetype :
        MIME type string identifying the backend.
        Defaults to ``"application/x-zarr"`` (``ZarrWriter``).
    **kwargs
        Additional keyword arguments forwarded to the writer constructor.
        Use these to pass backend-specific configuration derived from a YAML
        file without hardcoding the concrete class at the call site.

    Returns
    -------
    SharedDetectorWriter
        A freshly constructed writer instance.

    Raises
    ------
    ValueError
        If no registered backend matches *mimetype*.
    """
    match mimetype:
        case "application/x-zarr":
            from redsun.storage._zarr import ZarrWriter  # lazy — keeps _zarr private

            return ZarrWriter(name, **kwargs)
        case _:
            raise ValueError(
                f"No writer registered for mimetype: {mimetype!r}. "
                "Supported mimetypes: 'application/x-zarr'."
            )
