"""Which changed files let a pull request labelled docs-only skip the tests."""

from __future__ import annotations

import pytest

from scripts.docs_only import is_documentation, not_documentation


@pytest.mark.parametrize(
    ("path", "documentation"),
    [
        ("docs/how-to/place-a-view.md", True),
        ("docs/diagrams/style.d2", True),
        ("docs/explanation/decisions/COPYME", True),
        ("changelog.d/292.fixed.md", True),
        ("zensical.toml", True),
        ("README.md", True),
        ("docs/examples/acquisition.py", False),
        ("docs/tutorials/session.yaml", False),
        ("src/redsun/qt/_session.py", False),
        ("tests/configs/notes.md", False),
        (".github/workflows/ci.yaml", False),
        ("pyproject.toml", False),
        ("docs", False),
    ],
)
def test_a_path_is_documentation_or_not(path: str, documentation: bool) -> None:
    """Count pages, entries, the site config and root Markdown as documentation, and code under docs as code."""
    assert is_documentation(path) is documentation


def test_the_files_that_are_not_documentation_are_named_in_order() -> None:
    """Return every changed file that is not documentation, in the order given."""
    changed = [
        "docs/index.md",
        "src/redsun/aio.py",
        "changelog.d/1.added.md",
        "uv.lock",
    ]
    assert not_documentation(changed) == ["src/redsun/aio.py", "uv.lock"]
