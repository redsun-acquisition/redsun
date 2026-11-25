"""The `redsun` command."""

from __future__ import annotations

from importlib.resources import files
from typing import Annotated

import typer
import yaml

from redsun import __version__
from redsun.errors import BuildError, HookError

app = typer.Typer(
    name="redsun",
    add_completion=False,
    rich_markup_mode=None,
    pretty_exceptions_enable=False,
)
"""The `redsun` command, one function for each of its commands."""


def styles() -> list[str]:
    """Return the short names of the styles `redsun` ships.

    They are read from `redsun`'s own manifest alone, so the command starts
    without looking at the plugins installed beside it.
    """
    text = files("redsun").joinpath("plugins.yaml").read_text(encoding="utf-8")
    return sorted(yaml.safe_load(text).get("hooks", {}))


STYLES = styles()


def print_version(wanted: bool) -> None:
    """Print the installed version and end the command, if *wanted*."""
    if wanted:
        typer.echo(__version__)
        raise typer.Exit


def known_style(name: str | None) -> str | None:
    """Return *name* if it is `None` or the short name of a style.

    Raises
    ------
    typer.BadParameter
        If it is neither, listing the styles.
    """
    if name is not None and name not in STYLES:
        raise typer.BadParameter(
            f"no style named {name!r}; choose from {', '.join(STYLES)}"
        )
    return name


@app.callback(invoke_without_command=True)
def redsun(
    context: typer.Context,
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=print_version,
            is_eager=True,
            help="Print the installed version and exit.",
        ),
    ] = False,
) -> None:
    """Run what redsun ships."""
    if context.invoked_subcommand is None:
        # typer's own help for no argument exits with 2, as for a mistake
        typer.echo(context.get_help())


@app.command()
def example(
    style: Annotated[
        str | None,
        typer.Argument(
            callback=known_style,
            metavar="STYLE",
            show_default=False,
            help=(
                f"The style to open it in ({', '.join(STYLES)}); "
                "the platform's look when none is named."
            ),
        ),
    ] = None,
) -> None:
    """Open the example session, every built-in component over simulated devices."""
    try:
        # a Qt binding comes with an extra, and the command exists without one
        from redsun.examples import ExampleApp, example_config  # noqa: PLC0415
    except ImportError as e:
        typer.echo(
            f"The example needs a window, and a Qt binding could not be loaded ({e}). "
            "If none is installed, install 'redsun[pyqt]' or 'redsun[pyside]'.",
            err=True,
        )
        raise typer.Exit(1) from e
    try:
        ExampleApp(example_config(style)).run()
    except (BuildError, HookError, OSError) as e:
        typer.echo(f"The example could not start. {e}", err=True)
        raise typer.Exit(1) from e
