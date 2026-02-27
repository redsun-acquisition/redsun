from __future__ import annotations

from urllib.parse import urlparse
from urllib.request import url2pathname


def from_uri(uri: str) -> str:
    """Convert a URI to a filesystem path if local, otherwise return as-is.

    Parameters
    ----------
    uri : str
        The URI to convert.

    Returns
    -------
    str
        The filesystem path if the URI is a local file URI, otherwise the original URI.
    """
    parsed = urlparse(uri)
    if parsed.scheme == "file":
        return url2pathname(parsed.path)
    return uri


__all__ = [
    "from_uri",
]
