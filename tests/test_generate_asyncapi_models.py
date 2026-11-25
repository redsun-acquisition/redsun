"""The generated AsyncAPI models match the schema they are generated from."""

from __future__ import annotations

from typing import TYPE_CHECKING

from scripts import generate_asyncapi_models

if TYPE_CHECKING:
    import pytest


def test_committed_models_are_current() -> None:
    """Pass the check when the committed module equals a fresh generation."""
    assert generate_asyncapi_models.main(["--check"]) == 0


def test_stale_models_fail_the_check(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail the check when the module differs from what the generator writes."""
    monkeypatch.setattr(generate_asyncapi_models, "generate", lambda: "# edited\n")
    assert generate_asyncapi_models.main(["--check"]) == 1
