"""The example session served over HTTP. Needs the `fastapi` extra."""

from __future__ import annotations

from redsun.fastapi import FastAPISession

from ._core import ExampleCore


class ExampleWeb(FastAPISession, ExampleCore):
    """The example's devices and presenters, served by FastAPI."""
