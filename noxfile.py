import nox
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nox.sessions import Session

@nox.session(venv_backend="mamba", python=["3.9", "3.10", "3.11"])
def lint(session: "Session") -> None:
    session.conda_install("--file", "requirements-dev.txt")
    session.run("ruff", "check")
