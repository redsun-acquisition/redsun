from __future__ import annotations

import re


def session_folder(session: str) -> str:
    """Return the folder name *session*'s files, logs and catalog live under.

    Every run of characters other than letters, digits, `.`, `-` and `_`
    becomes one `_`, and leading and trailing dots go, so the name cannot
    climb out of its parent. A name with nothing left is `_`.
    """
    return re.sub(r"[^\w.-]+", "_", session).strip(".") or "_"
