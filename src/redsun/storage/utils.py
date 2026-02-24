from __future__ import annotations

from urllib.parse import urlparse
from urllib.request import url2pathname


def from_uri(uri: str) -> str:
    """Convert a URI to a filesystem path if local, otherwise return as-is."""
    parsed = urlparse(uri)
    if parsed.scheme == "file":
        return url2pathname(parsed.path)
    return uri
