"""Status object.

The Status class has been adapted from `ophyd <https://github.com/bluesky/ophyd>`_.
The ophyd license is reproduced below:

    Copyright (c) 2014, Brookhaven Science Associates, Brookhaven National
    Laboratory. All rights reserved.

    Redistribution and use in source and binary forms, with or without
    modification, are permitted provided that the following conditions are met:

    - Redistributions of source code must retain the above copyright notice, this \
    list of conditions and the following disclaimer.

    - Redistributions in binary form must reproduce the above copyright notice, \
    this list of conditions and the following disclaimer in the documentation \
    and/or other materials provided with the distribution.

    - Neither the name of the Brookhaven Science Associates, Brookhaven National \
    Laboratory nor the names of its contributors may be used to endorse or promote \
    products derived from this software without specific prior written permission.

    THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
    AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
    IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
    DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
    FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
    DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
    SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
    CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
    OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
    OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from typing import TYPE_CHECKING

from bluesky.protocols import Status as PStatus

from ._exceptions import InvalidState, StatusTimeoutError, WaitTimeoutError

if TYPE_CHECKING:
    from typing import Callable

__all__ = ["Status"]


class Status(PStatus):
    """
    Track the status of a potentially-lengthy action like moving or triggering.

    Parameters
    ----------
    timeout: float, optional
        The amount of time to wait before marking the Status as failed.  If
        ``None`` (default) wait forever. It is strongly encouraged to set a
        finite timeout.  If settle_time below is set, that time is added to the
        effective timeout.
    settle_time: float, optional
        The amount of time to wait between the caller specifying that the
        status has completed to running callbacks. Default is 0.

    Notes
    -----
    Theory of operation:

    This employs two ``threading.Event`` objects, one thread that runs for
    (timeout + settle_time) seconds, and one thread that runs for
    settle_time seconds (if settle_time is nonzero).

    At __init__ time, a *timeout* and *settle_time* are specified. A thread
    is started, on which user callbacks, registered after __init__ time via
    [`add_callback`](), will eventually be run. The thread waits on an
    Event be set or (timeout + settle_time) seconds to pass, whichever
    happens first.

    If (timeout + settle_time) expires and the Event has not
    been set, an internal Exception is set to ``StatusTimeoutError``, and a
    second Event is set, marking the Status as done and failed. The
    callbacks are run.

    If a callback is registered after the Status is done, it will be run
    immediately.

    If the first Event is set before (timeout + settle_time) expires,
    then the second Event is set and no internal Exception is set, marking
    the Status as done and successful. The callbacks are run.

    There are two methods that directly set the first Event. One,
    [`set_exception`](), sets it directly after setting the internal
    Exception.  The other, [`set_finished`](), starts a
    ``threading.Timer`` that will set it after a delay (the settle_time).
    One of these methods may be called, and at most once. If one is called
    twice or if both are called, ``InvalidState`` is raised. If they are
    called too late to prevent a ``StatusTimeoutError``, they are ignored
    but one call is still allowed. Thus, an external callback, e.g. pyepics,
    may reports success or failure after the Status object has expired, but
    to no effect because the callbacks have already been called and the
    program has moved on.
    """

    def __init__(self, *, timeout: float | None = None, settle_time: float | None = 0):
        super().__init__()
        self._logger = logging.getLogger("redsun")
        self._tname = None
        self._lock = threading.RLock()
        self._event = threading.Event()  # state associated with done-ness
        self._settled_event = threading.Event()
        # "Externally initiated" means set_finished() or set_exception(exc) was
        # called, as opposed to completion via an internal timeout.
        self._externally_initiated_completion_lock = threading.Lock()
        self._externally_initiated_completion = False
        self._callbacks: deque[Callable[[Status], None]] = deque()
        self._exception: BaseException | None = None

        if settle_time is None:
            settle_time = 0.0

        self._settle_time = float(settle_time)

        if timeout is not None:
            timeout = float(timeout)
        self._timeout = timeout

        self._callback_thread = threading.Thread(
            target=self._run_callbacks, daemon=True, name=self._tname
        )
        self._callback_thread.start()

    @property
    def timeout(self) -> float | None:
        """The timeout for this action.

        This is set when the Status is created, and it cannot be changed.
        """
        return self._timeout

    @property
    def settle_time(self) -> float:
        """A delay between when [`set_finished`]() is when the Status is done.

        This is set when the Status is created, and it cannot be changed.
        """
        return self._settle_time

    @property
    def done(self) -> bool:
        """Boolean indicating whether associated operation has completed.

        This is set to True at __init__ time or by calling
        [`set_finished`](), [`set_exception`]().
        Once True, it can never become False.
        """
        return self._event.is_set()

    @property
    def success(self) -> bool:
        """Boolean indicating whether associated operation has completed.

        This is set to True at __init__ time or by calling
        [`set_finished`](), [`set_exception`]()
        . Once True, it can never become False.
        """
        return self.done and self._exception is None

    def _handle_failure(self) -> None:
        """Do something if an exception occurred during the action."""
        # TODO: implement this; maybe ophyd has a good example
        pass

    def _settled(self) -> None:
        """Connect to this this when status has completed and settled."""
        # TODO: implement this; maybe ophyd has a good example
        pass

    def _run_callbacks(self) -> None:
        """Set the Event and run the callbacks."""
        if self.timeout is None:
            timeout = None
        else:
            timeout = self.timeout + self.settle_time
        if not self._settled_event.wait(timeout):
            # We have timed out. It's possible that set_finished() has already
            # been called but we got here before the settle_time timer expired.
            # And it's possible that in this space be between the above
            # statement timing out grabbing the lock just below,
            # set_exception(exc) has been called. Both of these possibilties
            # are accounted for.
            self._logger.warning("%r has timed out", self)
            with self._externally_initiated_completion_lock:
                # Set the exception and mark the Status as done, unless
                # set_exception(exc) was called externally before we grabbed
                # the lock.
                if self._exception is None:
                    exc = StatusTimeoutError(
                        f"Status {self!r} failed to complete in specified timeout."
                    )
                    self._exception = exc
        # Mark this as "settled".
        try:
            self._settled()
        except Exception:
            # No alternative but to log this. We can't supersede set_exception,
            # and we have to continue and run the callbacks.
            self._logger.exception("%r encountered error during _settled()", self)
        # Now we know whether or not we have succeed or failed, either by
        # timeout above or by set_exception(exc), so we can set the Event that
        # will mark this Status as done.
        with self._lock:
            self._event.set()
        if self._exception is not None:
            try:
                self._handle_failure()
            except Exception:
                self._logger.exception(
                    "%r encountered an error during _handle_failure()", self
                )
        # The callbacks have access to self, from which they can distinguish
        # success or failure.
        for cb in self._callbacks:
            try:
                cb(self)
            except Exception:
                self._logger.exception(
                    "An error was raised on a background thread while "
                    "running the callback %r(%r).",
                    cb,
                    self,
                )
        self._callbacks.clear()

    def set_exception(self, exc: BaseException) -> None:
        """Mark as finished but failed with the given Exception.

        This method should generally not be called by the *recipient* of this
        Status object, but only by the object that created and returned it.

        Parameters
        ----------
        exc: BaseException
            The exception that caused the failure.
        """
        # Since we rely on this being raise-able later, check proactively to
        # avoid potentially very confusing failures.
        if not (isinstance(exc, BaseException)):
            # Note that Python allows `raise Exception` or raise Exception()`
            # so we allow a class or an instance here too.
            raise ValueError(f"Expected an Exception, got {exc!r}")

        # Ban certain Timeout subclasses that have special significance. This
        # would probably never come up except due to some rare user error, but
        # if it did it could be very confusing indeed!
        for exc_class in (StatusTimeoutError, WaitTimeoutError):
            if isinstance(exc, exc_class):
                raise ValueError(
                    f"{exc_class} has special significance and cannot be set "
                    "as the exception. Use a plain TimeoutError or some other "
                    "subclass thereof."
                )

        with self._externally_initiated_completion_lock:
            if self._externally_initiated_completion:
                raise InvalidState(
                    "Either set_finished() or set_exception() has "
                    f"already been called on {self!r}"
                )
            self._externally_initiated_completion = True
            if isinstance(self._exception, StatusTimeoutError):
                # We have already timed out.
                return
            self._exception = exc
            self._settled_event.set()

    def set_finished(self) -> None:
        """Mark as finished successfully.

        This method should generally not be called by the *recipient* of this
        Status object, but only by the object that created and returned it.
        """
        with self._externally_initiated_completion_lock:
            if self._externally_initiated_completion:
                raise InvalidState(
                    "Either set_finished() or set_exception() has "
                    f"already been called on {self!r}"
                )
            self._externally_initiated_completion = True
        # Note that in either case, the callbacks themselves are run from the
        # same thread. This just sets an Event, either from this thread (the
        # one calling set_finished) or the thread created below.
        if self.settle_time > 0:
            threading.Timer(self.settle_time, self._settled_event.set).start()
        else:
            self._settled_event.set()

    def exception(self, timeout: float | None = None) -> BaseException | None:
        """Return the exception raised by the action.

        If the action has completed successfully, return ``None``. If it has
        finished in error, return the exception.

        Parameters
        ----------
        timeout: float | None, optional
            If None (default) wait indefinitely until the status finishes.

        Returns
        -------
        Exception:
            The exception raised by the action. If the action has completed
            successfully, return ``None``.

        Raises
        ------
        WaitTimeoutError
            If the status has not completed within ``timeout`` (starting from
            when this method was called, not from the beginning of the action).
        """
        if not self._event.wait(timeout=timeout):
            raise WaitTimeoutError("Status has not completed yet.")
        return self._exception

    def wait(self, timeout: float | None = None) -> None:
        """Block until the action completes.

        When the action has finished succesfully, return ``None``. If the
        action has failed, raise the exception.

        Parameters
        ----------
        timeout: ``float``, optional
            If ``None`` (default) wait indefinitely until the status finishes.

        Raises
        ------
        WaitTimeoutError
            If the status has not completed within ``timeout`` (starting from
            when this method was called, not from the beginning of the action).
        StatusTimeoutError
            If the status has failed because the *timeout* that it was
            initialized with has expired.
        Exception
            This is ``status.exception()``, raised if the status has finished
            with an error.  This may include ``TimeoutError``, which
            indicates that the action itself raised ``TimeoutError``, distinct
            from ``WaitTimeoutError`` above.
        """
        if not self._event.wait(timeout=timeout):
            raise WaitTimeoutError("Status has not completed yet.")
        if self._exception is not None:
            raise self._exception

    @property
    def callbacks(self) -> deque[Callable[[Status], None]]:
        """Callbacks to be run when the status is marked as finished."""
        return self._callbacks

    def add_callback(self, callback: Callable[[Status], None]) -> None:
        """Register a callback to be called once when the Status finishes.

        The callback will be called exactly once. If the Status is finished
        before a callback is added, it will be called immediately. This is
        threadsafe.
        The callback will be called regardless of success of failure. The
        callback has access to this status object, so it can distinguish success
        or failure by inspecting the object.

        Parameters
        ----------
        callback: ``Callable[[Status], None]``
            The callback to be called when the status is marked as finished.

            ```python
            def callback(status: Status) -> None:
                # Do something with the status object
                ...
            ```
        """
        with self._lock:
            if self.done:
                # Call it once and do not hold a reference to it.
                callback(self)
            else:
                # Hold a strong reference to this. In other contexts we tend to
                # hold weak references to callbacks, but this is a single-shot
                # callback, so we will hold a strong reference until we call it,
                # and then clear this cache to drop the reference(s).
                self._callbacks.append(callback)
