"""The example session served over HTTP. Needs the `fastapi` extra."""

from __future__ import annotations

from typing import ClassVar

from redsun.fastapi import FastAPISession, RemoteSettings

from ._core import ExampleCore


class ExampleWeb(FastAPISession, ExampleCore):
    """The example's devices and presenters, served by FastAPI."""

    remote: ClassVar[RemoteSettings] = {"origins": ["http://localhost:5173"]}
    """Allows the TypeScript client's development server."""
