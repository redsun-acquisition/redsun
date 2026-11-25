"""Generate `redsun.fastapi._asyncapi` from the official AsyncAPI 3.0.0 JSON Schema.

The schema in `scripts/asyncapi/` is cut down to the objects the document of
the event socket uses, and `datamodel-codegen` writes the pydantic models. With
`--check` nothing is written, and the exit status says whether the committed
module matches a fresh generation.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

SCHEMA = Path(__file__).parent / "asyncapi" / "asyncapi-3.0.0.json"
TARGET = Path(__file__).parent.parent / "src" / "redsun" / "fastapi" / "_asyncapi.py"

KEEP = {
    "": ["asyncapi", "info", "channels", "operations", "components"],
    "info": ["title", "version", "description"],
    "channel": ["address", "messages", "title", "summary", "description"],
    "operation": ["action", "channel", "messages", "title", "summary", "description"],
    "messageObject": [
        "contentType",
        "payload",
        "name",
        "title",
        "summary",
        "description",
    ],
    "components": ["schemas", "messages"],
}
"""The properties kept of each object, by the name of its definition."""

OPTIONS = [
    "--input-file-type=jsonschema",
    "--output-model-type=pydantic_v2.BaseModel",
    "--preset=standard-py311-20261124",
    "--target-python-version=3.11",
    "--class-name=AsyncAPI",
    "--disable-timestamp",
    "--formatters",
    "black",
    "isort",
]


def prune(node: dict[str, Any], names: list[str]) -> None:
    """Keep only the properties of *node* in *names*, and drop its patterns."""
    if "allOf" in node and "properties" in node["allOf"][0]:
        node.update(node.pop("allOf")[0])
    node["properties"] = {
        k: v for k, v in node.get("properties", {}).items() if k in names
    }
    if "required" in node:
        node["required"] = [r for r in node["required"] if r in names]
    for key in ("patternProperties", "allOf", "dependencies"):
        node.pop(key, None)


def reachable(node: Any, definitions: dict[str, Any], found: set[str]) -> None:
    """Add to *found* every definition *node* refers to, directly or not."""
    match node:
        case {"$ref": str(ref)} if ref.startswith("#/definitions/"):
            name = ref.rsplit("/", 1)[-1]
            if name not in found:
                found.add(name)
                reachable(definitions[name], definitions, found)
        case dict():
            for value in node.values():
                reachable(value, definitions, found)
        case list():
            for value in node:
                reachable(value, definitions, found)


def subset(schema: dict[str, Any]) -> dict[str, Any]:
    """Return *schema* cut down to what the document of the event socket uses.

    A message's payload and the schemas of the components are JSON Schema, not
    document structure, so they become plain JSON objects.
    """
    definitions = schema["definitions"]
    for name, names in KEEP.items():
        prune(schema if name == "" else definitions[name], names)
    definitions["messageObject"]["properties"]["payload"] = {
        "type": "object",
        "description": "JSON Schema of the payload.",
    }
    definitions["components"]["properties"]["schemas"] = {
        "type": "object",
        "additionalProperties": {"type": "object"},
    }
    found: set[str] = set()
    reachable(
        {k: v for k, v in schema.items() if k != "definitions"}, definitions, found
    )
    schema["definitions"] = {k: definitions[k] for k in sorted(found)}
    return schema


def generate() -> str:
    """Return the source of the models generated from the official schema."""
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as folder:
        source = Path(folder, "asyncapi-3.0.0-subset.json")
        output = Path(folder, "models.py")
        source.write_text(json.dumps(subset(schema), indent=1), encoding="utf-8")
        subprocess.run(
            [
                sys.executable,
                "-m",
                "datamodel_code_generator",
                "--input",
                str(source),
                "--output",
                str(output),
                *OPTIONS,
            ],
            check=True,
            cwd=folder,
        )
        return output.read_text(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    """Write the generated module, or with `--check` compare it to the committed one."""
    arguments = sys.argv[1:] if argv is None else argv
    source = generate()
    if "--check" in arguments:
        if TARGET.read_text(encoding="utf-8") == source:
            return 0
        print(f"{TARGET} is out of date: run scripts/generate_asyncapi_models.py")
        return 1
    TARGET.write_text(source, encoding="utf-8", newline="\n")
    print(f"wrote {TARGET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
