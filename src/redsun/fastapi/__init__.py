"""The web frontend: a session serving its presenters with FastAPI.

Needs the `fastapi` extra.
"""

from __future__ import annotations

from ._session import FastAPIFrontend, FastAPISession, RemoteSettings

__all__ = ["FastAPIFrontend", "FastAPISession", "RemoteSettings"]
