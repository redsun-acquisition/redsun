"""The `redsun` command."""

from __future__ import annotations

import argparse
import sys
from functools import partial
from typing import TYPE_CHECKING

from redsun import __version__
from redsun.errors import BuildError

from ._manifest import OWN_PLUGIN
from .session._plugins import manifest

if TYPE_CHECKING:
    from collections.abc import Sequence


def example_style(styles: Sequence[str], name: str) -> str:
    """Return *name* if it is empty or one of *styles*.

    Raises
    ------
    argparse.ArgumentTypeError
        If it is neither, listing the styles.
    """
    if name and name not in styles:
        raise argparse.ArgumentTypeError(
            f"no example named {name!r}; choose from {', '.join(styles)}"
        )
    return name


def parser() -> argparse.ArgumentParser:
    """Return the parser of the `redsun` command.

    The styles `--example` takes are the hook providers `redsun` lists by
    short name.
    """
    styles = sorted(manifest(OWN_PLUGIN).hooks)
    made = argparse.ArgumentParser(prog="redsun", description="Run what redsun ships.")
    made.add_argument("--version", action="version", version=__version__)
    made.add_argument(
        "--example",
        nargs="?",
        const="",
        type=partial(example_style, styles),
        metavar="STYLE",
        help=(
            "open the example session, every built-in component over "
            f"simulated devices, in the style named ({', '.join(styles)}), "
            "or in the platform's look when no style is named"
        ),
    )
    return made


def run_example(style: str) -> int:
    """Run the example session in *style*, the platform's look for an empty name.

    A session that starts ends the process when its window closes, so this
    returns only when the session could not start, with the exit code.
    """
    try:
        # a Qt binding comes with an extra, and the command exists without one
        from redsun.examples import ExampleApp, example_config  # noqa: PLC0415
    except ImportError as e:
        print(
            f"The example needs a window, and no Qt binding could be loaded ({e}). "
            "Install 'redsun[pyqt]' or 'redsun[pyside]'.",
            file=sys.stderr,
        )
        return 1
    try:
        ExampleApp(example_config(style or None)).run()
    except BuildError as e:
        print(f"The example could not be built. {e}", file=sys.stderr)
        return 1


def main(argv: Sequence[str] | None = None) -> int:
    """Run the `redsun` command with *argv*, the process's arguments for `None`, and return the exit code."""
    made = parser()
    arguments = made.parse_args(argv)
    if arguments.example is None:
        made.print_help()
        return 0
    return run_example(arguments.example)
