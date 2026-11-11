"""Messages between a process pool and a worker: a pipe, and shared-memory rings for large buffers."""

from __future__ import annotations

import contextlib
import logging
import pickle
from functools import cache
from typing import TYPE_CHECKING, Annotated, Any, Final, cast

import numpy as np

from ._pickling import PROTOCOL, dumps_call

if TYPE_CHECKING:
    import sys
    from collections.abc import Callable
    from multiprocessing.connection import Connection
    from types import ModuleType

    if sys.platform == "win32":
        from multiprocessing.connection import PipeConnection
    else:
        PipeConnection = Connection

RING_THRESHOLD: Final = 64 * 1024
"""Bytes above which a contiguous buffer travels through a ring rather than the pipe."""

RING_CAPACITY: Final = 4
"""Items a ring holds before its sender waits for the reader."""

PEER_CHECK: Final = 0.25
"""Seconds a send waits on a full ring before it checks the other end is still there."""

logger = logging.getLogger("redsun")


@cache
def rings() -> ModuleType | None:
    """Return `sharedbox`, or `None` and log once that it is not installed."""
    try:
        import sharedbox  # noqa: PLC0415
    except ImportError:
        logger.info(
            "sharedbox is not installed, so large arrays travel through the pipe; "
            "install redsun[sharedbox] for shared-memory rings"
        )
        return None
    return sharedbox


class UnreadableMessage(Exception):
    """Raised by `Channel.receive` for a message whose payload could not be unpickled."""

    def __init__(self, kind: str, id: int, error: Exception) -> None:
        super().__init__(f"{kind} {id} could not be read: {error}")
        self.kind = kind
        self.id = id
        self.error = error


def ring_item(box: ModuleType, size: int) -> object:
    """Return the item type of a ring holding buffers of up to *size* bytes."""
    return Annotated[np.ndarray, box.MaxShape((size,)), box.DType("uint8")]


class Channel:
    """One end of a pipe to another process.

    Each message is a kind, an id and a payload pickled with protocol 5. With
    `sharedbox` installed, every contiguous buffer above `RING_THRESHOLD` in a
    payload travels out of band, through a shared-memory ring this end creates
    and the other end attaches to. The ring grows to the largest buffer, at
    least doubling each time. Without `sharedbox`, every buffer stays in the
    pickle.
    """

    __slots__ = (
        "closed",
        "connection",
        "incoming",
        "outgoing",
        "reader",
        "ring_bytes",
        "ring_names",
        "sender",
    )

    def __init__(self, connection: Connection | PipeConnection) -> None:
        self.connection = connection
        self.outgoing: Any = None
        self.sender: Any = None
        self.incoming: Any = None
        self.reader: Any = None
        self.ring_bytes = 0
        """Item size of the ring this end sends on, 0 before the first large buffer."""
        self.ring_names: set[str] = set()
        """Every ring either end announced."""
        self.closed = False

    def send(self, kind: str, id: int, payload: object) -> None:
        """Send one message, its large buffers through the ring.

        A `call` payload is `(fn, args, kwargs)`.

        Raises
        ------
        TypeError
            If a `call` cannot be pickled; the message names the culprit.
        EOFError
            If the other end closed while a ring item waited for room.
        """
        box = rings()
        items: list[memoryview] = []

        def out_of_band(buffer: pickle.PickleBuffer) -> bool:
            try:
                raw = buffer.raw()
            except BufferError:
                return True
            if raw.nbytes <= RING_THRESHOLD:
                return True
            items.append(raw)
            return False

        callback = None if box is None else out_of_band
        if kind == "call":
            fn, args, kwargs = cast(
                "tuple[Callable[..., Any], tuple[Any, ...], dict[str, Any]]", payload
            )
            data = dumps_call(fn, args, kwargs, buffer_callback=callback)
        else:
            data = pickle.dumps(payload, protocol=PROTOCOL, buffer_callback=callback)
        if items:
            assert box is not None
            self.grow(box, max(item.nbytes for item in items))
        self.connection.send((kind, id, data, len(items)))
        for item in items:
            self.send_item(np.frombuffer(item, dtype=np.uint8))

    def send_item(self, item: np.ndarray[Any, Any]) -> None:
        """Send one ring item, checking the other end while the ring stays full.

        Raises
        ------
        EOFError
            If the other end closed the pipe.
        """
        while True:
            try:
                self.sender.send(item, timeout=PEER_CHECK)
            except TimeoutError:
                # the other end sends nothing while it reads ring items, so a
                # readable or broken pipe means it closed
                try:
                    gone = self.connection.poll()
                except OSError:
                    gone = True
                if gone:
                    raise EOFError(
                        "the other end closed while a ring was full"
                    ) from None
            else:
                return

    def receive(self) -> tuple[str, int, Any]:
        """Return the next message, with the buffers it sent through the ring.

        Raises
        ------
        EOFError
            If the other end has closed.
        UnreadableMessage
            If the payload could not be unpickled; the channel stays usable.
        """
        while True:
            kind, id, data, count = self.connection.recv()
            if kind != "ring":
                break
            self.attach(*data)
        items = []
        if count:
            box = rings()
            assert box is not None
            try:
                items = [self.reader.receive() for _ in range(count)]
            except box.EndOfStream as error:
                raise EOFError(
                    "the other end closed before sending every ring item"
                ) from error
        try:
            return kind, id, pickle.loads(data, buffers=items)
        except Exception as error:
            raise UnreadableMessage(kind, id, error) from error

    def grow(self, box: ModuleType, needed: int) -> None:
        """Replace the sending ring with one holding *needed* bytes, unless it already does.

        The other end attaches to the new ring before the old one is closed and
        unlinked.
        """
        if needed <= self.ring_bytes:
            return
        size = max(needed, 2 * self.ring_bytes)
        stream = box.SharedStream.create(ring_item(box, size), capacity=RING_CAPACITY)
        self.ring_names.add(stream.name)
        self.connection.send(("ring", 0, (stream.name, size), 0))
        kind, _, _, _ = self.connection.recv()
        if kind != "attached":
            stream.close()
            box.SharedStream.unlink(stream.name)
            raise RuntimeError(f"expected the other end to attach, not {kind!r}")
        old = self.outgoing
        self.outgoing, self.sender, self.ring_bytes = stream, stream.sender(), size
        if old is not None:
            old.close()
            box.SharedStream.unlink(old.name)

    def attach(self, name: str, size: int) -> None:
        """Read the ring the other end announced from now on, and tell it so."""
        box = rings()
        assert box is not None
        if self.incoming is not None:
            self.incoming.close()
        self.ring_names.add(name)
        self.incoming = box.SharedStream.attach(ring_item(box, size), name)
        self.reader = self.incoming.reader(mode="lossless", start="oldest")
        self.connection.send(("attached", 0, None, 0))

    def close(self) -> None:
        """Close the pipe and both rings, and unlink every ring either end announced."""
        if self.closed:
            return
        self.closed = True
        self.connection.close()
        for stream in (self.outgoing, self.incoming):
            if stream is not None:
                stream.close()
        # a closed sender or reader still maps its ring until it is freed, and
        # on Windows the ring lasts as long as any mapping does
        self.outgoing = self.sender = self.incoming = self.reader = None
        box = rings()
        if box is None:
            return
        for name in self.ring_names:
            # the other end may have unlinked it first
            with contextlib.suppress(box.SegmentNotFoundError):
                box.SharedStream.unlink(name)
