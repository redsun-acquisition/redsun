"""The web frontend: a session serving its presenters with FastAPI.

Needs the `fastapi` extra.
"""

from __future__ import annotations

from ._session import FastAPIFrontend, FastAPISession

__all__ = ["FastAPIFrontend", "FastAPISession"]
