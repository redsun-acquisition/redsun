"""Type-level assertions for services declared on a session.

Never imported or executed; checked by the project's normal mypy invocation.
"""

from __future__ import annotations

from typing import Annotated, TypeAlias, assert_type

from psygnal import SignalInstance

from redsun import AsService, Attach, Launch, Session
from redsun.services import Service

CameraIoc: TypeAlias = Annotated[AsService, Launch("mylab.iocs.camera")]


class App(Session):
    ioc: AsService
    camera_ioc: CameraIoc
    beamline: Annotated[AsService, Attach("BL01:")]


def check_a_service_attribute_is_a_service(app: App) -> None:
    assert_type(app.ioc, Service)
    assert_type(app.ioc.sig_exited, SignalInstance)
    assert_type(app.camera_ioc, Service)
    assert_type(app.beamline, Service)
