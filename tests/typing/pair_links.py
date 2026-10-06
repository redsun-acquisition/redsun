"""`links_between` returns links a `wire` method can yield.

Never imported or executed; checked by the project's normal mypy invocation.
"""

from __future__ import annotations

from typing import assert_type

from redsun import Link, links_between

assert_type(links_between(object(), object()), list[Link])
