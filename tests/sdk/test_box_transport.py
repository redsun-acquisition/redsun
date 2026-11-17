"""The service side of the sharedbox transport."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re
import sys
import time
from collections.abc import AsyncGenerator, Awaitable
from functools import partial
from typing import Any
from uuid import uuid4

import numpy as np
import pytest
import pytest_asyncio
from fastcs.control_system import FastCS
from fastcs.controllers import Controller
from mock_pkg.box_controller import BoxController, Mode, TableController
from sharedbox import (
    RequestError,
    RequestSupersededError,
    SegmentNotFoundError,
    SharedBox,
)

from redsun.services._layout import (
    ControllerDescription,
    ServiceIndex,
    box_class,
    index_name,
    walk,
)
from redsun.services._process import announce_when_reachable, log_failed_announcement
from redsun.services.sharedbox import BoxTransport
from tests.sdk.helpers import messages


class Service:
    """The client side of a served controller: the description and the attached boxes."""

    def __init__(self, prefix: str) -> None:
        self.prefix = prefix
        self.index: ServiceIndex
        self.root: ControllerDescription
        self.boxes: dict[str, SharedBox] = {}

    async def attach(self) -> None:
        async with asyncio.timeout(5):
            while True:
                try:
                    self.index = ServiceIndex.attach(index_name(self.prefix))
                    break
                except SegmentNotFoundError:
                    await asyncio.sleep(0.01)
        self.root = json.loads(self.index.description)
        for description in walk(self.root):
            if description["box"] is not None:
                self.boxes[description["box"]] = box_class(description).attach(
                    description["box"]
                )

    def box_of(self, *path: str) -> Any:
        """Return the attached box of the child controller at `path`."""
        description = self.root
        for part in path:
            description = description["children"][part]
        assert description["box"] is not None
        return self.boxes[description["box"]]

    def close(self) -> None:
        for box in (*self.boxes.values(), self.index):
            box.close()


def serving(
    controller: Controller, prefix: str | None = None
) -> tuple[Service, asyncio.Task[None]]:
    prefix = prefix or f"T{uuid4().hex[:8]}"
    controller.set_path([prefix])
    fastcs = FastCS(controller, [BoxTransport()], loop=asyncio.get_running_loop())
    task = asyncio.create_task(fastcs.serve(interactive=False))
    return Service(prefix), task


async def answered(future: Awaitable[Any]) -> Any:
    """Wait for the answer to a request, at most five seconds."""
    async with asyncio.timeout(5):
        return await future


async def until(condition: Any) -> None:
    async with asyncio.timeout(5):
        while not condition():
            await asyncio.sleep(0.005)


@pytest_asyncio.fixture
async def served() -> AsyncGenerator[tuple[BoxController, Service], None]:
    controller = BoxController()
    service, task = serving(controller)
    await service.attach()
    yield controller, service
    service.close()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


async def test_the_index_describes_the_controller_tree(
    served: tuple[BoxController, Service],
) -> None:
    """Describe attributes, commands and the vector children in the index."""
    _, service = served
    root = service.root
    assert root["path"] == []
    assert re.fullmatch(
        re.escape(service.prefix) + r":fastcs:[0-9a-f]{6}:root", root["box"] or ""
    )
    assert root["children"]["axes"]["children"]["1"]["path"] == ["axes", "1"]
    assert root["children"]["axes"]["children"]["1"]["box"] == f"{root['box']}:axes:1"
    assert root["commands"] == ["run"]
    assert root["attributes"]["exposure"]["access"] == "rw"
    assert root["attributes"]["exposure"]["datatype"] == {
        "kind": "float",
        "units": "ms",
        "min": 0.0,
        "precision": 2,
    }
    assert root["attributes"]["label"]["access"] == "r"
    assert root["attributes"]["label"]["datatype"] == {"kind": "str", "capacity": 8}
    assert root["attributes"]["limited"]["datatype"] == {"kind": "int", "max": 10}
    assert root["attributes"]["big"]["datatype"]["kind"] == "uint"
    assert root["attributes"]["mode"]["datatype"] == {
        "kind": "enum",
        "names": ["IDLE", "RUN"],
    }
    assert list(root["children"]) == ["axes"]
    assert list(root["children"]["axes"]["children"]) == ["0", "1"]
    assert root["children"]["axes"]["box"] is None


async def test_a_request_is_put_and_answered(
    served: tuple[BoxController, Service],
) -> None:
    """Put the value of a request to the controller and publish it as the setpoint."""
    controller, service = served
    top = service.box_of()
    await answered(top.exposure.set(2.0))
    assert controller.exposure.get() == 2.0
    assert top.exposure.setpoint == 2.0
    assert top.exposure.value == 2.0

    await answered(top.mode.set(1))
    assert controller.mode.get() is Mode.RUN
    assert top.mode.value == 1

    await answered(top.big.set(np.uint64(2**63 + 5)))
    assert controller.big.get() == 2**63 + 5
    assert int(top.big.value) == 2**63 + 5


async def test_a_refused_put_is_answered_with_its_error(
    served: tuple[BoxController, Service],
) -> None:
    """Raise RequestError with FastCS's message for an out-of-range put, then accept a valid one."""
    controller, service = served
    top = service.box_of()
    with pytest.raises(RequestError, match=r"greater than maximum 10\S*$"):
        await answered(top.limited.set(11))
    assert controller.limited.get() == 0

    await answered(top.limited.set(3))
    assert controller.limited.get() == 3


async def test_an_overtaken_request_is_superseded(
    served: tuple[BoxController, Service],
) -> None:
    """Supersede the earlier of two requests sent while the handler is held, and put the later."""
    controller, service = served
    controller.put_delay = 0.05
    top = service.box_of()
    held = top.slow.set(1)
    await asyncio.sleep(0.01)
    overtaken = top.slow.set(2)
    latest = top.slow.set(3)
    with pytest.raises(RequestSupersededError):
        await answered(overtaken)
    await answered(held)
    await answered(latest)
    assert controller.slow_seen == 3


async def test_a_command_runs_on_request(
    served: tuple[BoxController, Service],
) -> None:
    """Run the command once per request."""
    controller, service = served
    top = service.box_of()
    await answered(top.run())
    await answered(top.run())
    assert controller.runs == 2


async def test_an_update_reaches_the_box(
    served: tuple[BoxController, Service],
) -> None:
    """Publish a value the controller changes into the box of a vector child, with a later time."""
    controller, service = served
    child = service.box_of("axes", "1")
    before = time.time_ns()
    await controller.axes[1].position.update(1.25)
    await until(lambda: child.position.value == 1.25)
    assert child.position.read()["timestamp_ns"] > before


async def test_a_write_only_attribute_publishes_what_it_accepted(
    served: tuple[BoxController, Service],
) -> None:
    """Publish the accepted value of a write-only attribute as its value and its setpoint."""
    _, service = served
    top = service.box_of()
    before = time.time_ns()
    await answered(top.slow.set(4))
    reading = top.slow.read()
    assert reading["value"] == 4
    assert reading["setpoint"] == 4
    assert reading["timestamp_ns"] > before


async def test_a_long_string_is_cut_to_its_field(
    served: tuple[BoxController, Service], caplog: pytest.LogCaptureFixture
) -> None:
    """Cut a string to the field's capacity in UTF-8 bytes and warn, instead of failing."""
    controller, service = served
    top = service.box_of()
    await controller.label.update("abcééé")
    await until(lambda: top.label.value != "start")
    assert top.label.value == "abcéé"
    assert messages(caplog, logging.WARNING) == [
        "'label' holds 8 bytes, so a value of 9 bytes was cut"
    ]


async def test_a_table_attribute_is_refused_at_connect() -> None:
    """Raise ValueError naming the table attribute."""
    controller = TableController()
    controller.set_path([f"T{uuid4().hex[:8]}"])
    fastcs = FastCS(controller, [BoxTransport()], loop=asyncio.get_running_loop())
    with pytest.raises(ValueError, match="rows"):
        await fastcs.serve(interactive=False)


@pytest.mark.skipif(
    sys.platform == "win32", reason="Windows keeps a segment while a handle is open"
)
async def test_boxes_are_closed_when_serving_stops() -> None:
    """Unlink the index when the serving task is cancelled."""
    service, task = serving(BoxController())
    await service.attach()
    service.close()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    with pytest.raises(SegmentNotFoundError):
        ServiceIndex.attach(index_name(service.prefix))


async def test_a_prefix_with_colons_names_the_boxes() -> None:
    """Name boxes under a prefix that holds colons and a trailing colon."""
    tag = uuid4().hex[:8]
    service, task = serving(BoxController(), f"T{tag}:DET:")
    try:
        await service.attach()
        root = service.root["box"] or ""
        assert re.fullmatch(f"T{tag}:DET:fastcs:[0-9a-f]{{6}}:root", root)
        assert f"{root}:axes:0" in service.boxes
        service.close()
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_a_restart_names_its_boxes_anew_while_a_client_holds_the_old_ones() -> (
    None
):
    """Publish under a new run name though a handle to the first run's box is open."""
    prefix = f"T{uuid4().hex[:8]}"
    first, task = serving(BoxController(), prefix)
    await first.attach()
    first.index.close()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)

    second, task = serving(BoxController(), prefix)
    try:
        await second.attach()
        assert second.root["box"] != first.root["box"]
    finally:
        for box in first.boxes.values():
            box.close()
        second.close()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_a_value_the_box_cannot_hold_names_the_attribute(
    served: tuple[BoxController, Service],
) -> None:
    """Raise an error naming the attribute when its box refuses a value."""
    controller, _ = served
    with pytest.raises(ValueError, match="'limited'"):
        await controller.limited.update(-(2**70))


async def test_a_transport_that_cannot_tell_it_is_reachable_is_logged(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Log the error of a transport whose `reachable` raises."""
    transport = BoxTransport()

    async def refuse() -> None:
        raise RuntimeError("index lost")

    monkeypatch.setattr(transport, "reachable", refuse)
    task = asyncio.ensure_future(announce_when_reachable(transport, "SIM"))
    task.add_done_callback(partial(log_failed_announcement, "SIM"))
    with contextlib.suppress(RuntimeError):
        await task

    assert messages(caplog, logging.ERROR) == [
        "SIM could not tell it is ready: index lost"
    ]
