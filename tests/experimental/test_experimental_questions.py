"""A `setup` parameter typed by a protocol is answered by what satisfies it."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Protocol

import pytest

from redsun.experimental import AsPresenter, AsView, Placement, Session, provides

if TYPE_CHECKING:
    from .conftest import BuildSession


class HasLayers(Protocol):
    def add_layer(self, name: str) -> None: ...


class HasCamera(Protocol):
    def snap(self) -> bytes: ...


class HasRoi(Protocol):
    roi: tuple[int, int]


class HasStage(Protocol):
    def move(self, to: float) -> None: ...


class Resettable(Protocol):
    def reset(self) -> None: ...


class ViewerModel:
    """A concrete object one component makes and shares."""

    def __init__(self) -> None:
        self.layers: list[str] = []

    def add_layer(self, name: str) -> None:
        self.layers.append(name)


class Somewhere(Placement):
    """A placement the default frontend accepts, which attaches nothing."""


class Imager:
    def __init__(self, name: str) -> None:
        self.name = name
        self.model = ViewerModel()

    @provides
    def viewer(self) -> ViewerModel:
        return self.model

    def reset(self) -> None: ...


class Camera:
    """A component nothing wires and that shares nothing: only a question reaches it."""

    def __init__(self, name: str) -> None:
        self.name = name

    def snap(self) -> bytes:
        return b""


class Stage:
    """A component sharing itself, so it is reachable two ways."""

    def __init__(self, name: str) -> None:
        self.name = name

    @provides
    def itself(self) -> Stage:
        return self

    def move(self, to: float) -> None: ...


class Overlay:
    def __init__(self, name: str) -> None:
        self.name = name

    def setup(
        self,
        viewer: ViewerModel,
        layers: HasLayers,
        camera: HasCamera,
        stage: HasStage,
        resettable: Mapping[str, Resettable],
        roi: HasRoi | None = None,
    ) -> None:
        self.viewer = viewer
        self.layers = layers
        self.camera = camera
        self.stage = stage
        self.resettable = resettable
        self.roi = roi

    def reset(self) -> None: ...


class Snapper:
    """Asks for the one camera, which is itself or nothing."""

    def __init__(self, name: str) -> None:
        self.name = name

    def setup(self, camera: HasCamera) -> None:
        self.camera = camera

    def snap(self) -> bytes:
        return b""


class Broken:
    """A camera whose constructor fails."""

    def __init__(self, name: str) -> None:
        raise RuntimeError("no camera attached")

    def snap(self) -> bytes:
        return b""


class CameraView:
    """A view that is also a camera."""

    placement: Placement = Somewhere()

    def __init__(self, name: str) -> None:
        self.name = name

    def snap(self) -> bytes:
        return b""


class AnswersApp(Session):
    imager: AsPresenter[Imager]
    camera: AsPresenter[Camera]
    stage: AsPresenter[Stage]
    overlay: AsPresenter[Overlay]


class NoCameraApp(Session):
    snapper: AsPresenter[Snapper]


class TwoCamerasApp(Session):
    first: AsPresenter[Camera]
    second: AsPresenter[Camera]
    snapper: AsPresenter[Snapper]


class BrokenCameraApp(Session):
    camera: AsPresenter[Broken]
    snapper: AsPresenter[Snapper]


class ViewCameraApp(Session):
    camera: AsView[CameraView]
    snapper: AsPresenter[Snapper]


def test_setup_is_answered_by_type_and_by_protocol(
    build: BuildSession, caplog: pytest.LogCaptureFixture
) -> None:
    """A shared object answers its own type and every protocol it satisfies."""
    app = build(AnswersApp)
    imager = app.presenters["imager"]
    overlay = app.presenters["overlay"]
    assert isinstance(imager, Imager)
    assert isinstance(overlay, Overlay)

    assert overlay.viewer is imager.model
    assert overlay.layers is imager.model
    camera: object = app.presenters["camera"]
    stage: object = app.presenters["stage"]
    assert overlay.camera is camera
    assert overlay.stage is stage
    assert overlay.roi is None
    assert set(overlay.resettable) == {"imager", "overlay"}
    assert "'camera' shares nothing" not in caplog.text


@pytest.mark.parametrize(
    ("app", "match"),
    [
        (NoCameraApp, "nothing in the session does"),
        (TwoCamerasApp, "but 2 do, from 'first', 'second'"),
        (ViewCameraApp, "'camera', which is a view"),
    ],
    ids=["none-but-itself", "several", "later-layer"],
)
def test_a_question_the_session_cannot_answer_is_refused(
    app: type[Session], match: str
) -> None:
    with pytest.raises(TypeError, match=match):
        app().build()


def test_a_question_only_a_failed_component_answers_leaves_the_asker_not_set_up(
    build: BuildSession, caplog: pytest.LogCaptureFixture
) -> None:
    app = build(BrokenCameraApp)

    assert "snapper" in app.presenters
    assert "Not set up: snapper (presenter)" in caplog.text
    assert "'camera' was not built" in caplog.text
