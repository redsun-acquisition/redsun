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

    from event_model.documents import (
        Event,
        EventDescriptor,
        RunStart,
        RunStop,
        StreamResource,
    )
    from numpy.typing import DTypeLike, NDArray

    from ._base import Stream
    from ._placement import Placement

__all__ = ["Writer"]

logger = logging.getLogger("redsun")

Store = tuple[str, str]


@dataclass(slots=True)
class Product:
    """One product: given whole by `declare`, or laid out and stored as a run's *source* is."""

    data_key: str
    source: str | None = None
    layout: ArrayShape | None = None
    store: Store | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Open:
    """A stream open on one store, and the products it was opened with."""

    stream: Stream
    placement: Placement
    products: list[Product]


@dataclass(slots=True)
class Run:
    """What a run's documents said so far, and the streams opened for it.

    Keyed by source data key: the layout its `descriptor` gave and the store
    its `stream_resource` named. ``uid`` is ``None`` for the streams opened
    outside any run.
    """

    uid: str | None
    layouts: dict[str, ArrayShape] = field(default_factory=dict)
    stores: dict[str, Store] = field(default_factory=dict)
    open: dict[Path, Open] = field(default_factory=dict)
    unplaced: set[str] = field(default_factory=set)


class Writer(DocumentRouter):
    """Write the products a component computes against the stores a run names.

    A product is declared once, before the run: `declare` with a layout and a
    store, or `derive` from a data key of the run, whose `descriptor` gives
    the layout and whose `stream_resource` gives the store. The component
    forwards every document it receives with ``writer(name, doc)`` and hands
    the data over itself, `append` per frame or `write` for the whole
    product. A run's `stop` closes the streams opened for it and writes each
    product's metadata: the component's mapping as given, and a ``redsun``
    mapping naming the run, the source, the store and the time.

    A store's stream opens on the first `append` or `write` against it, with
    every product of that store known by then. A product resolves against
    the innermost open run whose documents named both its layout and its
    store, so a nested run sees what the run around it declared.
    """

    def __init__(self) -> None:
        super().__init__()
        self._products: dict[str, Product] = {}
        self._runs: list[Run] = []
        self._outside = Run(uid=None)

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
            If *data_key* was not declared, no open run named its layout and
            store, or it goes to a store of its own, which is written whole.
        """
        opened = self._stream_for(data_key, whole=None)
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
        finished at the run's `stop`; one placed as a store of its own is
        finished at once, its layout taken from *data*.

        Raises
        ------
        WriterError
            If *data_key* was not declared, no open run named its layout and
            store, or the run described its store with a mimetype no writer
            knows.
        """
        opened = self._stream_for(data_key, whole=data)
        if opened is None:
            raise WriterError(
                f"{data_key!r} cannot be written: no writer for its store"
            )
        self._product(data_key).metadata = dict(metadata or {})
        opened.stream.append(data_key, data)
        if not opened.placement.streamed:
            run = self._run_of(data_key)
            self._finish(run.open.pop(opened.placement.path), run)
        return opened.placement.uri

    def close(self) -> None:
        """Finish every open stream, write its metadata, and forget every run."""
        for run in (*self._runs, self._outside):
            self._close(run)
        self._runs.clear()

    def shutdown(self) -> None:
        """Close, so a session ending mid-run leaves every store readable."""
        self.close()

    def start(self, doc: RunStart) -> None:
        """Open a run; one started inside another is the innermost until its stop."""
        self._runs.append(Run(uid=doc["uid"]))

    def descriptor(self, doc: EventDescriptor) -> None:
        """Take the layout of every derived product's source this stream describes."""
        run = self._find(doc["run_start"])
        for source in {product.source for product in self._products.values()}:
            key = doc["data_keys"].get(source or "")
            if key is None or source is None:
                continue
            dtype = key.get("dtype_numpy")
            shape = tuple(size for size in key["shape"] if size is not None)
            if dtype is None or len(shape) != len(key["shape"]):
                logger.warning(
                    f"{source!r} is described without dtype_numpy or with a "
                    "size left open; nothing derived from it has a layout."
                )
                continue
            run.layouts[source] = ArrayShape.of(shape, dtype)

    def stream_resource(self, doc: StreamResource) -> None:
        """Take the store of every derived product's source this resource names."""
        self._find(doc["run_start"]).stores[doc["data_key"]] = (
            doc["uri"],
            doc["mimetype"],
        )

    def event(self, doc: Event) -> Event:
        """Pass an event through: data reaches the writer by `append` and `write`."""
        return doc

    def stop(self, doc: RunStop) -> None:
        """Close the streams opened for this run and forget what it said."""
        run = self._find(doc["run_start"])
        self._close(run)
        if run is not self._outside:
            self._runs.remove(run)

    def _product(self, data_key: str) -> Product:
        """Return the product declared as *data_key*."""
        try:
            return self._products[data_key]
        except KeyError:
            raise WriterError(
                f"{data_key!r} was not declared; declare or derive it before the run"
            ) from None

    def _find(self, uid: str) -> Run:
        """Return the open run *uid*, or the streams outside any run for one not open."""
        for run in reversed(self._runs):
            if run.uid == uid:
                return run
        return self._outside

    def _in(self, product: Product, run: Run) -> tuple[ArrayShape, Store] | None:
        """Return the layout and store of *product* as *run* knows them."""
        if product.source is None:
            if product.layout is None or product.store is None:
                return None
            return product.layout, product.store
        layout = run.layouts.get(product.source)
        store = run.stores.get(product.source)
        if layout is None or store is None:
            return None
        return layout, store

    def _run_of(self, data_key: str) -> Run:
        """Return the innermost open run that names the product's layout and store.

        Raises
        ------
        WriterError
            Naming what no open run said.
        """
        product = self._product(data_key)
        for run in (*reversed(self._runs), self._outside):
            if self._in(product, run) is not None:
                return run
        described = any(product.source in run.layouts for run in self._runs)
        missing, document = (
            ("store", "stream_resource") if described else ("layout", "descriptor")
        )
        raise WriterError(
            f"{data_key!r} has no {missing} yet: no {document} of an open run "
            f"named its source {product.source!r}"
        )

    def _stream_for(self, data_key: str, *, whole: NDArray[Any] | None) -> Open | None:
        """Return the stream *data_key* goes to, opening it on the first call.

        ``None`` when the run described the store with a mimetype no writer
        knows, logged once per run. *whole* is the whole product when the
        caller has it, which a store of its own needs.
        """
        product = self._product(data_key)
        run = self._run_of(data_key)
        known = self._in(product, run)
        assert known is not None
        _, (uri, mimetype) = known
        if data_key in run.unplaced:
            return None
        placed = placement(uri, mimetype, data_key)
        if placed is None:
            logger.warning(
                f"{data_key!r} is not written: no writer for {mimetype!r} at {uri}."
            )
            run.unplaced.add(data_key)
            return None
        if not placed.streamed and whole is None:
            raise WriterError(
                f"{data_key!r} is written as a store of its own, whole: "
                "use write instead of append"
            )
        opened = run.open.get(placed.path)
        if opened is None:
            if placed.streamed:
                arrays = {
                    other.data_key: known[0]
                    for other in self._products.values()
                    if (known := self._in(other, run)) is not None
                    and known[1] == (uri, mimetype)
                }
            else:
                arrays = {data_key: ArrayShape.of(whole.shape, whole.dtype)}  # type: ignore[union-attr]
            products = [self._products[key] for key in arrays]
            opened = Open(placed.open(arrays), placed, products)
            run.open[placed.path] = opened
        elif product not in opened.products:
            raise WriterError(
                f"the stream on {placed.path} was opened without {data_key!r}; "
                "declare every product of a store before the first append"
            )
        return opened

    def _close(self, run: Run) -> None:
        """Finish every stream of *run* and forget what its documents said."""
        while run.open:
            self._finish(run.open.popitem()[1], run)
        run.layouts.clear()
        run.stores.clear()
        run.unplaced.clear()

    def _finish(self, opened: Open, run: Run) -> None:
        """Close *opened* and write both metadata mappings on each of its products."""
        opened.stream.close()
        written = datetime.now(UTC).isoformat(timespec="seconds")
        for product in opened.products:
            known = self._in(product, run)
            provenance: dict[str, Any] = {
                "run_start": run.uid,
                "resource_uri": known[1][0] if known is not None else None,
                "written": written,
            }
            if product.source is not None:
                provenance["source"] = product.source
            merge_attributes(
                opened.stream.node(product.data_key),
                {**product.metadata, "redsun": provenance},
            )
            product.metadata = {}
