"""The sharedbox transport is a name a session file may give, and sets no environment."""

from __future__ import annotations

import os

from redsun._config import session_file_schema, validate_session
from redsun.services._transports import TRANSPORTS


def test_a_session_file_may_name_the_sharedbox_transport() -> None:
    """Accept `sharedbox` as `services.transport`, and list it in the schema."""
    session = validate_session([], {"services": {"transport": "sharedbox"}})

    assert session.transport == "sharedbox"
    services, _ = session_file_schema()["properties"]["services"]["anyOf"]
    assert "sharedbox" in services["properties"]["transport"]["enum"]


def test_the_sharedbox_transport_sets_no_environment() -> None:
    """Leave the environment alone when a sharedbox service is reserved, published or attached."""
    transport = TRANSPORTS["sharedbox"]
    before = dict(os.environ)

    assert transport.reserve("svc") == {}
    transport.publish("svc")
    transport.attach("127.0.0.1:5064")

    assert dict(os.environ) == before
