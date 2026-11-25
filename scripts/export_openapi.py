"""Write the OpenAPI document of the example session served over the web.

The document is the one `session.app.openapi()` gives, with the arguments of
each presenter's signals under the top-level key `x-redsun-signals`, and the
schema `RedsunEvent`, one `oneOf` entry per served signal, in its components.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from redsun.examples._web import ExampleWeb
from redsun.fastapi._schemas import signal_adapters, signal_schema
from redsun.ports._remote import served


def event_schema(signals: dict[str, dict[str, list[dict[str, Any]]]]) -> dict[str, Any]:
    """Return the schema of a WebSocket message: one entry per presenter and signal."""
    return {
        "oneOf": [
            {
                "type": "object",
                "properties": {
                    "presenter": {"const": presenter},
                    "signal": {"const": signal},
                    "args": {
                        "type": "array",
                        "prefixItems": arguments,
                        "items": False,
                        "minItems": len(arguments),
                        "maxItems": len(arguments),
                    },
                },
                "required": ["presenter", "signal", "args"],
                "additionalProperties": False,
            }
            for presenter, by_signal in signals.items()
            for signal, arguments in by_signal.items()
        ]
    }


def main(argv: list[str]) -> None:
    """Build the example headless, write its OpenAPI document to the path in *argv*, and shut it down."""
    (target,) = argv
    session = ExampleWeb()
    session.build()
    try:
        document = session.app.openapi()
        document["x-redsun-signals"] = {
            name: signal_schema(signal_adapters(presenter, what, {}))
            for name, presenter in session.presenters.items()
            if (what := served(presenter)) is not None
        }
        document["components"]["schemas"]["RedsunEvent"] = event_schema(
            document["x-redsun-signals"]
        )
        Path(target).write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    finally:
        session.shutdown()
    print(f"wrote {target}")


if __name__ == "__main__":
    main(sys.argv[1:])
