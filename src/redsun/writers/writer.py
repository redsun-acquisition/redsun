"""A writer that follows a run's documents to place the products a component computes."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from event_model import DocumentRouter

from ._base import ArrayShape, WriterError, merge_attributes
from ._placement import placement

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from event_model.documents import EventDescriptor, RunStart, RunStop, StreamResource
    from numpy.typing import DTypeLike, NDArray

    from ._base import Stream
    from ._placement import Placement

__all__ = ["Writer"]

logger = logging.getLogger("redsun")


@dataclass(slots=True)
class Product:
    """What the writer knows about one product, filled by declaration or by documents."""

    data_key: str
    source: str | None = None
    layout: ArrayShape | None = None
    store: tuple[str, str] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    unplaced: bool = False

    @property
    def declared(self) -> bool:
        """Whether the layout and store were given, rather than read from a run."""
        return self.source is None


@dataclass(slots=True)
class Open:
    """A stream open on one store, and the products it was opened with."""

    stream: Stream
    placement: Placement
    products: list[Product]


class Writer(DocumentRouter):
    """Write the products a component computes against the stores a run names.

    A product is declared once, before the run: `declare` with a layout and a
    store, or `derive` from a data key of the run, whose `descriptor` gives
    the layout and whose `stream_resource` gives the store. The component
    forwards every document it receives with ``writer(name, doc)`` and hands
    the data over itself, `append` per frame or `write` for the whole
    product. `stop` closes every stream and writes each product's metadata:
    the component's mapping as given, and a ``redsun`` mapping naming the
    run, the source, the store and the time.

    A store's stream opens on the first `append` or `write` against it, with
    every product of that store known by then. One run at a time: a `start`
    arriving while streams are open closes them first.
    """

    def __init__(self) -> None:
        super().__init__()
        self._products: dict[str, Product] = {}
        self._open: dict[Path, Open] = {}
        self._run: str | None = None

    def declare(
        self, data_key: str, *, shape: tuple[int, ...], dtype: DTypeLike, store: str
    ) -> None:
        """Declare a product of frames shaped *shape*, written as a key of the Zarr store at *store*."""
        self._products[data_key] = Product(
            data_key,
            layout=ArrayShape.of(shape, dtype),
            store=(store, "application/x-zarr"),
        )

    def derive(self, data_key: str, *, source: str) -> None:
        """Declare a product laid out and stored as the run's *source* data key is."""
        self._products[data_key] = Product(data_key, source=source)

    def append(self, data_key: str, data: NDArray[Any]) -> None:
        """Append one frame, or a stack of frames, to *data_key*.

        Raises
        ------
        WriterError
            If *data_key* was not declared, has no layout or store yet, or
            goes to a store of its own, which is written whole.
        """
        opened = self._stream_for(data_key, whole=False)
        if opened is not None:
            opened.stream.append(data_key, data)

    def write(
        self,
        data_key: str,
        data: NDArray[Any],
        metadata: Mapping[str, Any] | None = None,
    ) -> str:
        """Write the whole of *data_key* and return the URI of where it went.

        A product placed as a key of the run's store is appended to it and
        finished at `stop`; one placed as a store of its own is finished at
        once, its layout taken from *data*.

        Raises
        ------
        WriterError
            If *data_key* was not declared, or has no store yet, or the run
            described its store with a mimetype no writer knows.
        """
        product = self._product(data_key)
        if product.store is not None and product.layout is None:
            product.layout = ArrayShape.of(data.shape, data.dtype)
        opened = self._stream_for(data_key, whole=True)
        if opened is None:
            raise WriterError(
                f"{data_key!r} cannot be written: no writer for "
                f"{product.store[1] if product.store else None!r}"
            )
        product.metadata = dict(metadata or {})
        opened.stream.append(data_key, data)
        if not opened.placement.streamed:
            self._finish(self._open.pop(opened.placement.path))
        return opened.placement.uri

    def close(self) -> None:
        """Finish every open stream, write its metadata, and forget what the run filled in."""
        while self._open:
            self._finish(self._open.popitem()[1])
        for product in self._products.values():
            if not product.declared:
                product.layout = None
                product.store = None
            product.metadata = {}
            product.unplaced = False
        self._run = None

    def shutdown(self) -> None:
        """Close, so a session ending mid-run leaves every store readable."""
        self.close()

    def start(self, doc: RunStart) -> None:
        """Take the run's uid; a run still open is closed first."""
        if self._open:
            logger.warning(
                f"Run {self._run} left {len(self._open)} stream(s) open; "
                "closing them before the next run."
            )
            self.close()
        self._run = doc["uid"]

    def descriptor(self, doc: EventDescriptor) -> None:
        """Take the layout of every derived product whose source this stream describes."""
        for product in self._products.values():
            key = doc["data_keys"].get(product.source or "")
            if key is None or product.layout is not None:
                continue
            dtype = key.get("dtype_numpy")
            shape = tuple(size for size in key["shape"] if size is not None)
            if dtype is None or len(shape) != len(key["shape"]):
                logger.warning(
                    f"{product.source!r} is described without dtype_numpy or "
                    f"with a size left open; {product.data_key!r} has no layout "
                    "to be written with."
                )
                continue
            product.layout = ArrayShape.of(shape, dtype)

    def stream_resource(self, doc: StreamResource) -> None:
        """Take the store of every derived product whose source this resource names."""
        for product in self._products.values():
            if product.source == doc["data_key"]:
                product.store = (doc["uri"], doc["mimetype"])

    def stop(self, doc: RunStop) -> None:
        """Close every stream the run opened."""
        self.close()

    def _product(self, data_key: str) -> Product:
        """Return the product declared as *data_key*."""
        try:
            return self._products[data_key]
        except KeyError:
            raise WriterError(
                f"{data_key!r} was not declared; declare or derive it before the run"
            ) from None

    def _stream_for(self, data_key: str, *, whole: bool) -> Open | None:
        """Return the stream *data_key* goes to, opening it on the first call.

        ``None`` when the run described the store with a mimetype no writer
        knows, logged once per run. *whole* is whether the caller has the
        whole product, which a store of its own needs.
        """
        product = self._product(data_key)
        if product.layout is None or product.store is None:
            missing = "layout" if product.layout is None else "store"
            raise WriterError(
                f"{data_key!r} has no {missing} yet: no "
                f"{'descriptor' if missing == 'layout' else 'stream_resource'} "
                f"named its source {product.source!r}"
            )
        if product.unplaced:
            return None
        uri, mimetype = product.store
        placed = placement(uri, mimetype, data_key)
        if placed is None:
            logger.warning(
                f"{data_key!r} is not written: no writer for {mimetype!r} at {uri}."
            )
            product.unplaced = True
            return None
        if not placed.streamed and not whole:
            raise WriterError(
                f"{data_key!r} is written as a store of its own, whole: "
                "use write instead of append"
            )
        opened = self._open.get(placed.path)
        if opened is None:
            products = (
                [product]
                if not placed.streamed
                else [
                    other
                    for other in self._products.values()
                    if other.store == product.store and other.layout is not None
                ]
            )
            arrays = {
                other.data_key: other.layout
                for other in products
                if other.layout is not None
            }
            opened = Open(placed.open(arrays), placed, products)
            self._open[placed.path] = opened
        elif product not in opened.products:
            raise WriterError(
                f"the stream on {placed.path} was opened without {data_key!r}; "
                "declare every product of a store before the first append"
            )
        return opened

    def _finish(self, opened: Open) -> None:
        """Close *opened* and write both metadata mappings on each of its products."""
        opened.stream.close()
        written = datetime.now(UTC).isoformat(timespec="seconds")
        for product in opened.products:
            provenance: dict[str, Any] = {
                "run_start": self._run,
                "resource_uri": product.store[0] if product.store else None,
                "written": written,
            }
            if product.source is not None:
                provenance["source"] = product.source
            merge_attributes(
                opened.stream.node(product.data_key),
                {**product.metadata, "redsun": provenance},
            )
