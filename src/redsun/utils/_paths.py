from __future__ import annotations

import re


def session_folder(session: str) -> str:
    """Return the folder name for *session*'s files, logs and catalog.

    Each run of characters other than letters, digits, `.`, `-` and `_`
    becomes `_`, and outer dots go, so the name stays inside its parent. An
    empty result is `_`.
    """
    return re.sub(r"[^\w.-]+", "_", session).strip(".") or "_"
