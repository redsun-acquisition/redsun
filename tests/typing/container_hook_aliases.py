"""Type-level assertions for the container hook protocol aliases.

Never imported or executed: a type checker verifies these declarations.
The container hook points are parameterised on the container they act against
so that one vocabulary serves more than one container implementation; an alias
binds them, and a provider written against the wrong container fails
statically, which no runtime check can see - `isinstance` cannot be given a
parameterised protocol.

Checked by the project's normal mypy invocation; see CLAUDE.md.
"""

from __future__ import annotations

from redsun.containers import (
    AppConfiguresBuild,
    AppConfiguresSession,
    AppContainer,
    ConfiguresBuild,
)


class OtherContainer:
    """A container of another implementation, unrelated to `AppContainer`."""


class AppProvider:
    """Serves both container hook points of an `AppContainer`."""

    def configure_build(self, container: AppContainer) -> None: ...

    def configure_session(self, container: AppContainer) -> None: ...


class OtherProvider:
    """Serves the same points, against an unrelated container."""

    def configure_build(self, container: OtherContainer) -> None: ...

    def configure_session(self, container: OtherContainer) -> None: ...


def takes_build(_: AppConfiguresBuild) -> None: ...
def takes_session(_: AppConfiguresSession) -> None: ...
def takes_other_build(_: ConfiguresBuild[OtherContainer]) -> None: ...


def check_an_app_provider_satisfies_the_aliases(provider: AppProvider) -> None:
    takes_build(provider)
    takes_session(provider)


def check_a_provider_for_another_container_is_refused(
    provider: OtherProvider,
) -> None:
    takes_build(provider)  # type: ignore[arg-type]
    takes_session(provider)  # type: ignore[arg-type]


def check_the_same_protocol_binds_another_container(provider: OtherProvider) -> None:
    takes_other_build(provider)
