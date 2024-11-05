import nox
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nox.sessions import Session

    from typing import List

python_versions = ["3.9", "3.10", "3.11"]

@nox.session(venv_backend="mamba", python=python_versions)
def lint(session: "Session") -> None:
    session.conda_install("ruff")
    session.run("ruff", "check")

@nox.session(venv_backend="mamba", python=python_versions)
def mypy(session: "Session") -> None:
    requirements : "List[str]" = nox.project.load_toml("pyproject.toml")["project"]["dependencies"]
    session.install(*requirements, "mypy")
    session.run("mypy", "redsun", "--disable-error-code=import-untyped")

@nox.session(venv_backend="mamba", python=python_versions)
def test(session: "Session") -> None:
    requirements : "List[str]" = nox.project.load_toml("pyproject.toml")["project"]["dependencies"]
    session.install(*requirements, "pytest")
    session.run("pytest", "-v", "tests")
