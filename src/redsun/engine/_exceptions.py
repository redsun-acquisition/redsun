# Bluesky-specific exceptions, adapted from yaqc-bluesky
# Used primarily in redsun.engine.status

# BSD 3-Clause License

# Copyright (c) 2020, yaqc-bluesky developers
# All rights reserved.

# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:

# 1. Redistributions of source code must retain the above copyright notice, this
#    list of conditions and the following disclaimer.

# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.

# 3. Neither the name of the copyright holder nor the names of its contributors
#    may be used to endorse or promote products derived from this software
#    without specific prior written permission.

# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

__all__ = [
    "BlueskyException",
    "InvalidState",
    "UnknownStatusFailure",
    "StatusTimeoutError",
    "WaitTimeoutError",
]


class BlueskyException(Exception):
    """Bluesky base exception class."""

    pass


class InvalidState(RuntimeError, BlueskyException):
    """When Status.set_finished() or Status.set_exception(exc) is called too late."""

    ...


class UnknownStatusFailure(BlueskyException):
    """Generic error when a Status object is marked success=False without details."""

    ...


class StatusTimeoutError(TimeoutError, BlueskyException):
    """Timeout specified when a Status object was created has expired."""

    ...


class WaitTimeoutError(TimeoutError, BlueskyException):
    """TimeoutError raised when we ware waiting on completion of a task.

    This is distinct from TimeoutError, just as concurrent.futures.TimeoutError
    is distinct from TimeoutError, to differentiate when the task itself has
    raised a TimeoutError.
    """

    ...
