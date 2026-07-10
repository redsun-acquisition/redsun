from __future__ import annotations

import asyncio
from enum import Enum, auto

__all__ = [
    "InvalidStoreState",
    "StorageStateMachine",
    "StorageState",
]


class StorageState(Enum):
    """State of the storage lifecycle."""

    UNSEALED = auto()
    """Storage not yet open."""

    SEALING = auto()
    """Storage is in the process of being sealed."""

    OPEN = auto()
    """Storage is open and writing."""

    CLOSING = auto()
    """Last stream released, storage is in the process of being closed."""


class InvalidStoreState(RuntimeError):
    """Raised when an operation is attempted in an invalid store state.

    Parameters
    ----------
    state : StorageState
        The state in which the operation was attempted.
    verb : str
        The operation attempted.
    """

    def __init__(self, state: StorageState, verb: str) -> None:
        super().__init__(f"Cannot {verb} while store is {state.name}")
        self.state = state
        self.verb = verb


class StorageStateMachine:
    """State machine for managing the lifecycle of a storage backend."""

    __slots__ = ("_state", "_opened", "_closed", "_open_exc")

    @property
    def state(self) -> StorageState:
        """Current storage state."""
        return self._state

    def __init__(self) -> None:
        self._state = StorageState.UNSEALED
        self._opened = asyncio.Event()
        self._closed = asyncio.Event()
        self._closed.set()
        self._open_exc: BaseException | None = None

    async def ensure_registrable(self) -> None:
        """Ensure that the storage is in a state that allows registration of new streams.

        Behaves differently based on the current state:

        - UNSEALED: returns immediatly;
        - CLOSING: waits for the store to close;
        - SEALING / OPEN: raises InvalidStoreState.

        Raises
        ------
        InvalidStoreState
            If the store is in SEALING or OPEN state.
        """
        while self._state is StorageState.CLOSING:
            await self._closed.wait()
        if self._state is not StorageState.UNSEALED:
            raise InvalidStoreState(self._state, "register")

    def try_seal(self) -> bool:
        """Attempt to seal the storage.

        Transits from UNSEALED to SEALING state.

        Returns
        -------
            bool: True if the transition was successful, False otherwise.

        Raises
        ------
        InvalidStoreState
            If the store is in CLOSING state.
        """
        if self._state is StorageState.UNSEALED:
            self._state = StorageState.SEALING
            # clear previous internal state
            self._opened.clear()
            self._open_exc = None
            return True
        if self._state is StorageState.CLOSING:
            raise InvalidStoreState(self._state, "seal")
        return False

    def open_succeeded(self) -> None:
        """Call to ensure that transition SEALING -> OPEN is done and any waiters are notified.

        Raises
        ------
        InvalidStoreState
            If the store is not in SEALING state.
        """
        if self._state is not StorageState.SEALING:
            raise InvalidStoreState(self._state, "confirm open")
        self._state = StorageState.OPEN
        self._opened.set()

    def open_failed(self, exc: BaseException) -> None:
        """Call when opening failed, ensuring the transition SEALING -> UNSEALED.

        Parameters
        ----------
        exc: BaseException
            The exception that caused the opening to fail.

        Raises
        ------
        InvalidStoreState
            If the store is not in SEALING state.
        """
        if self._state is not StorageState.SEALING:
            raise InvalidStoreState(self._state, "fail open")
        self._state = StorageState.UNSEALED
        self._open_exc = exc
        self._opened.set()

    async def await_open(self) -> None:
        """Wait for the store to be opened.

        Raises
        ------
        BaseException
            Whatever exception is stashed by `open_failed`, if any.
        """
        await self._opened.wait()
        if self._open_exc is not None:
            raise self._open_exc

    def begin_close(self) -> None:
        """Begin the transition OPEN -> CLOSING.

        Raises
        ------
        InvalidStoreState
            If the store is not in OPEN state.
        """
        if self._state is not StorageState.OPEN:
            raise InvalidStoreState(self._state, "close")
        self._state = StorageState.CLOSING
        self._closed.clear()

    def close_finished(self) -> None:
        """Call to ensure that transition CLOSING -> UNSEALED is done and any waiters are notified.

        Raises
        ------
        InvalidStoreState
            If the store is not in CLOSING state.
        """
        if self._state is not StorageState.CLOSING:
            raise InvalidStoreState(self._state, "finish close")
        self._state = StorageState.UNSEALED
        self._closed.set()
