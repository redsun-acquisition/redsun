"""The service side of the sharedbox transport."""

from __future__ import annotations

import asyncio
import json
import re
import sys
from collections.abc import AsyncGenerator
from typing import Any
from uuid import uuid4

import numpy as np
import pytest
import pytest_asyncio
from fastcs.control_system import FastCS
from fastcs.controllers import Controller
from mock_pkg.box_controller import BoxController, Mode, TableController
from sharedbox import SegmentNotFoundError, SharedBox

from redsun.services._layout import (
    ControllerDescription,
    box_class,
    index_class,
    index_name,
)
from redsun.services.sharedbox import BoxTransport


class Service:
    """The client side of a served controller: the description and the attached boxes."""

    def __init__(self, prefix: str) -> None:
        self.prefix = prefix
        self.index: SharedBox
        self.root: ControllerDescription
        self.boxes: dict[str, SharedBox] = {}

    async def attach(self) -> None:
        async with asyncio.timeout(5):
            while True:
                try:
                    self.index = index_class().attach(index_name(self.prefix))
                    break
                except SegmentNotFoundError:
                    await asyncio.sleep(0.01)
        self.root = json.loads(self.index.snapshot()["description"])
        for description in self.walk(self.root):
            if description["box"] is not None:
                self.boxes[description["box"]] = box_class(description).attach(
                    description["box"]
                )

    def walk(self, description: ControllerDescription) -> list[ControllerDescription]:
        found = [description]
        for child in description["children"].values():
            found.extend(self.walk(child))
        return found

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


async def request(box: Any, stem: str, **values: Any) -> None:
    """Write the values, bump `<stem>__request` and wait until the service answers."""
    number = getattr(box, f"{stem}__request") + 1
    box.update(**values, **{f"{stem}__request": number})
    async with asyncio.timeout(5):
        while getattr(box, f"{stem}__done") < number:
            await asyncio.sleep(0.005)


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
    """Put the setpoint on request, answer without an error and update the readback."""
    controller, service = served
    top = service.box_of()
    await request(top, "exposure", exposure__setpoint=12.5)
    assert top.exposure__error == ""
    assert controller.exposure.get() == 12.5
    assert top.exposure__value == 12.5

    await request(top, "mode", mode__setpoint=1)
    assert controller.mode.get() is Mode.RUN
    assert top.mode__value == 1

    await request(top, "big", big__setpoint=np.array([2**63 + 5], dtype="uint64"))
    assert controller.big.get() == 2**63 + 5
    assert int(top.big__value[0]) == 2**63 + 5


async def test_a_refused_put_is_answered_with_its_error(
    served: tuple[BoxController, Service],
) -> None:
    """Answer an out-of-range put with FastCS's message, then clear it on success."""
    controller, service = served
    top = service.box_of()
    await request(top, "limited", limited__setpoint=11)
    assert "greater than maximum 10" in top.limited__error
    assert controller.limited.get() == 0

    await request(top, "limited", limited__setpoint=3)
    assert top.limited__error == ""
    assert controller.limited.get() == 3


async def test_every_request_up_to_the_latest_is_served(
    served: tuple[BoxController, Service],
) -> None:
    """Serve the latest request when several arrive while a put is running."""
    controller, service = served
    controller.put_delay = 0.05
    top = service.box_of()
    top.update(slow__setpoint=1, slow__request=1)
    await asyncio.sleep(0.01)
    top.update(slow__setpoint=2, slow__request=2)
    top.update(slow__setpoint=3, slow__request=3)
    await until(lambda: top.slow__done == 3)
    assert controller.slow_seen == 3


async def test_a_command_runs_on_request(
    served: tuple[BoxController, Service],
) -> None:
    """Run the command once per request."""
    controller, service = served
    top = service.box_of()
    await request(top, "run")
    await request(top, "run")
    assert controller.runs == 2
    assert top.run__error == ""


async def test_an_update_reaches_the_box(
    served: tuple[BoxController, Service],
) -> None:
    """Write a value the controller changes into the box of a vector child."""
    controller, service = served
    child = service.box_of("axes", "1")
    await controller.axes[1].position.update(1.25)
    await until(lambda: child.position__value == 1.25)


async def test_a_long_string_is_cut_to_its_field(
    served: tuple[BoxController, Service],
) -> None:
    """Cut a string to the field's capacity in UTF-8 bytes instead of failing."""
    controller, service = served
    top = service.box_of()
    await controller.label.update("abcééé")
    await until(lambda: top.label__value != "start")
    assert top.label__value == "abcéé"


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
        index_class().attach(index_name(service.prefix))


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
