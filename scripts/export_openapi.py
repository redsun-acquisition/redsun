"""Write the OpenAPI and AsyncAPI documents of the example session served over the web.

The two documents are the ones the session serves at `/openapi.json` and
`/asyncapi.json`, written as `openapi.json` and `asyncapi.json` in the
directory given.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from fastapi.routing import APIRoute

from redsun.examples._web import ExampleWeb


def main(argv: list[str]) -> None:
    """Build the example headless, write its two documents to the directory in *argv*, and shut it down."""
    (target,) = argv
    session = ExampleWeb()
    session.build()
    try:
        asyncapi = next(
            route.endpoint
            for route in session.app.routes
            if isinstance(route, APIRoute) and route.path == "/asyncapi.json"
        )
        documents = {
            "openapi.json": session.app.openapi(),
            "asyncapi.json": asyncio.run(asyncapi()),
        }
        for name, document in documents.items():
            path = Path(target, name)
            path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
            print(f"wrote {path}")
    finally:
        session.shutdown()


if __name__ == "__main__":
    main(sys.argv[1:])
