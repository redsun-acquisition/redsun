"""The `redsun` command."""

from __future__ import annotations

from importlib.resources import files
from typing import Annotated

import typer
import yaml

from redsun import __version__
from redsun.errors import BuildError, HookError

from ._reports import GROUPS, plugins_report

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
    web: Annotated[
        bool,
        typer.Option(
            "--web",
            help="Serve the example over HTTP instead of opening a window.",
        ),
    ] = False,
) -> None:
    """Open the example session, every built-in component over simulated devices."""
    if web:
        if style is not None:
            raise typer.BadParameter(
                "the example served over HTTP has no style", param_hint="STYLE"
            )
        serve_example()
        return
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


def serve_example() -> None:
    """Serve the example session over HTTP until Ctrl+C.

    Raises
    ------
    typer.Exit
        With code 1 when the web frontend is missing or the session cannot
        start.
    """
    try:
        # the web frontend comes with an extra, and the command exists without one
        from redsun.examples._web import ExampleWeb  # noqa: PLC0415
    except ImportError as e:
        typer.echo(
            f"Serving the example needs the web frontend, which could not be loaded ({e}). "
            "If it is not installed, install 'redsun[fastapi]'.",
            err=True,
        )
        raise typer.Exit(1) from e
    try:
        ExampleWeb().serve()
    except (BuildError, HookError, OSError, RuntimeError) as e:
        typer.echo(f"The example could not start. {e}", err=True)
        raise typer.Exit(1) from e


@app.command()
def plugins(
    as_json: Annotated[
        bool, typer.Option("--json", help="Print the report as JSON.")
    ] = False,
) -> None:
    """List the installed plugins and what each one offers."""
    report = plugins_report()
    if as_json:
        typer.echo(report.to_json())
        return
    for plugin in report.plugins:
        source = " ".join(filter(None, (plugin.distribution, plugin.version)))
        typer.echo(f"{plugin.plugin_name} ({source})" if source else plugin.plugin_name)
        for group in GROUPS:
            ids = [entry.plugin_id for entry in plugin.entries if entry.group == group]
            if ids:
                typer.echo(f"  {group}: {', '.join(ids)}")
    if report.problems:
        typer.echo("Skipped:")
        for problem in report.problems:
            typer.echo(f"  {problem.where}: {problem.message}")
