"""The test of the guide "How to run background processing"."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np
from event_model import compose_run

from docs.examples.background_median import MedianPresenter

if TYPE_CHECKING:
    import numpy.typing as npt

    from redsun import ThreadExecutor


# --8<-- [start:test]
def test_the_median_of_a_run(inline_threads: ThreadExecutor) -> None:
    """Publish the median of the frames when the run stops."""
    presenter = MedianPresenter("median", inline_threads, source="camera")
    published: list[npt.NDArray[Any]] = []
    presenter.sig_median.connect(published.append)
    run = compose_run()
    stream = run.compose_descriptor(
        name="primary",
        data_keys={"camera": {"source": "sim", "dtype": "array", "shape": [2, 2]}},
    )

    presenter("start", dict(run.start_doc))
    for value in (1, 5, 3):
        frame = np.full((2, 2), value)
        event = stream.compose_event(data={"camera": frame}, timestamps={"camera": 0})
        presenter("event", dict(event))
    presenter("stop", dict(run.compose_stop()))

    assert np.array_equal(published[0], np.full((2, 2), 3))


# --8<-- [end:test]
