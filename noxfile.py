import nox
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nox.sessions import Session

python_versions = ["3.9", "3.10", "3.11"]

@nox.session(venv_backend="mamba", python=python_versions)
def lint(session: "Session") -> None:
    session.conda_install("ruff")
    session.run("ruff", "check")

@nox.session(venv_backend="mamba", python=python_versions)
def mypy(session: "Session") -> None:
    session.conda_install("mypy")
    session.run("mypy", "redsun")

@nox.session(venv_backend="mamba", python=python_versions)
def test(session: "Session") -> None:
    session.conda_install("pytest")
    session.run("pytest", "-v", "tests")
