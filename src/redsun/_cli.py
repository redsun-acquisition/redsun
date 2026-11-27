"""The `redsun` command."""

from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path  # noqa: TC003
from typing import Annotated, Any

import typer
import yaml

from redsun import DesktopSession, Session, __version__
from redsun.errors import BuildError, HookError

from ._check import check_report
from ._config import frontends
from ._describe import describe_report
from ._reports import GROUPS, CheckReport, DescribeReport, plugins_report
from .session._profile import ProfileKind  # noqa: TC001

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


@app.command()
def check(
    files: Annotated[
        list[Path],
        typer.Argument(
            help="The session files, merged in the order given.",
            metavar="FILE",
            show_default=False,
        ),
    ],
    as_json: Annotated[
        bool, typer.Option("--json", help="Print the report as JSON.")
    ] = False,
) -> None:
    """Check whether the session the files describe would build, without building it."""
    report = check_report(files)
    if as_json:
        typer.echo(report.to_json())
    else:
        print_check(report)
    failed = any(c.status == "failed" for c in report.components) or any(
        lookup.status == "failed" for lookup in report.lookups
    )
    if report.problems or failed:
        raise typer.Exit(1)


def print_check(report: CheckReport) -> None:
    """Print *report* one line per record, each section only when it has any."""
    if report.problems:
        typer.echo("problems:")
        for problem in report.problems:
            typer.echo(f"  {problem.where}: {problem.message}")
    if report.components:
        typer.echo("components:")
        for component in report.components:
            source = ", ".join(
                filter(
                    None,
                    (
                        component.plugin_name
                        and f"{component.plugin_name}:{component.plugin_id}",
                        component.class_path,
                    ),
                )
            )
            line = f"  {component.status:<10} {component.group:<10} {component.name}"
            line += f"   ({source})" if source else ""
            typer.echo(line + (f" - {component.reason}" if component.reason else ""))
    if report.lookups:
        typer.echo("lookups:")
        for lookup in report.lookups:
            line = f"  {lookup.status:<10} {lookup.section:<10} {lookup.name}"
            typer.echo(line + (f" - {lookup.reason}" if lookup.reason else ""))
    typer.echo("not checked:")
    typer.echo(f"  {', '.join(report.skipped)}")


@app.command()
def describe(
    plugin: Annotated[
        str, typer.Argument(help="The plugin, as a session file names it.")
    ],
    plugin_id: Annotated[
        str | None,
        typer.Argument(
            help="One device, presenter or view of the plugin; all of them when left out.",
            metavar="ID",
            show_default=False,
        ),
    ] = None,
    as_json: Annotated[
        bool, typer.Option("--json", help="Print the report as JSON.")
    ] = False,
) -> None:
    """Describe the keys each device, presenter and view of a plugin takes."""
    report = describe_report(plugin, plugin_id)
    if as_json:
        typer.echo(report.to_json())
    else:
        print_describe(report)
    if report.problems or any(c.status == "failed" for c in report.components):
        raise typer.Exit(1)


def kind_of(schema: dict[str, Any]) -> str:
    """Return the type a JSON Schema allows, in a few words."""
    if "enum" in schema:
        return "one of " + ", ".join(map(str, schema["enum"]))
    if "type" in schema:
        return str(schema["type"])
    if "anyOf" in schema:
        return " or ".join(kind_of(part) for part in schema["anyOf"])
    if "$ref" in schema:
        return str(schema["$ref"]).rsplit("/", 1)[-1]
    return "any"


def print_describe(report: DescribeReport) -> None:
    """Print *report* as one block per component, then its problems."""
    typer.echo(report.plugin_name)
    for component in report.components:
        typer.echo(
            f"  {component.group}/{component.plugin_id} ({component.class_path})"
        )
        if component.status == "failed":
            typer.echo(f"    failed: {component.reason}")
            continue
        schema = component.json_schema or {}
        required = set(schema.get("required", []))
        from_service = {
            way["required"][0]
            for item in schema.get("allOf", [])
            for way in item["anyOf"][:1]
        }
        for key, value in schema.get("properties", {}).items():
            if key in ("plugin_name", "plugin_id"):
                continue
            line = f"    {key}: {kind_of(value)}"
            if "default" in value:
                line += f" = {json.dumps(value['default'])}"
            elif key in from_service:
                line += ", required, or from a service"
            else:
                line += ", required" if key in required else ", optional"
            typer.echo(line)
        if component.session:
            filled = ", ".join(f"{p.name} ({p.type})" for p in component.session)
            typer.echo(f"    the session fills: {filled}")
    if report.problems:
        typer.echo("Problems:")
        for problem in report.problems:
            typer.echo(f"  {problem.where}: {problem.message}")


# typer reads the annotations at runtime, so `Path` and `ProfileKind` are real imports
@app.command()
def run(
    files: Annotated[
        list[Path],
        typer.Argument(
            metavar="FILE",
            show_default=False,
            help="The session files, merged in the order given.",
        ),
    ],
    log_level: Annotated[
        str | None,
        typer.Option(help="The level the session logs at, such as DEBUG."),
    ] = None,
    profile: Annotated[
        ProfileKind | None,
        typer.Option(help="Profile the session's start, or its whole run."),
    ] = None,
    profile_dir: Annotated[
        Path | None,
        typer.Option(help="The folder the profile is written to."),
    ] = None,
    mock: Annotated[
        bool, typer.Option("--mock", help="Connect every device to a simulation.")
    ] = False,
    strict: Annotated[
        bool,
        typer.Option("--strict", help="Stop when a component fails to build."),
    ] = False,
) -> None:
    """Run the session the files describe, with the frontend they name."""
    sources: list[Path | dict[str, bool]] = [*files]
    if mock:
        sources.append({"mock": True})
    if strict:
        sources.append({"strict": True})
    try:
        session = Session.from_config(
            sources, log_level=log_level, profile=profile, profile_dir=profile_dir
        )
        if not isinstance(session, DesktopSession):
            typer.echo(
                "The session names no frontend, so it has nothing to show. Name "
                f"one with the 'frontend' key: {', '.join(sorted(frontends()))}.",
                err=True,
            )
            raise typer.Exit(1)
        session.run()
    # a bad file or a failed build raises one of these; anything else is a bug,
    # and catching `Exception` would print it as one line and hide its traceback
    except (BuildError, HookError, ImportError, OSError, TypeError, ValueError) as e:
        typer.echo(f"The session could not start. {e}", err=True)
        raise typer.Exit(1) from e
