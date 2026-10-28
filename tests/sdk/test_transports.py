"""The sharedbox transport is a name a session file may give."""

from __future__ import annotations

from redsun._config import session_file_schema, validate_session


def test_a_session_file_may_name_the_sharedbox_transport() -> None:
    """Accept `sharedbox` as `services.transport`, and list it in the schema."""
    session = validate_session([], {"services": {"transport": "sharedbox"}})

    assert session.transport == "sharedbox"
    services, _ = session_file_schema()["properties"]["services"]["anyOf"]
    assert "sharedbox" in services["properties"]["transport"]["enum"]
