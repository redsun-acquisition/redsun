"""What loading a session file refuses, and what its JSON schema refuses."""

from __future__ import annotations

import re
from typing import Any

import jsonschema
import pytest

from redsun import ConfigurationError
from redsun._config import session_file_schema, validate_session
from redsun._manifest import PluginManifest

ENTRY = {"plugin_name": "redsun", "plugin_id": "positioner"}


@pytest.mark.parametrize(
    ("section", "where"),
    [
        *(
            pytest.param(
                {"presenters": {"p": {**ENTRY, "workers": workers}}},
                "presenters.p.workers",
                id=f"workers-{workers!r}",
            )
            for workers in (0, -3, "four", True, 2.5)
        ),
        pytest.param(
            {"views": {"v": {**ENTRY, "workers": 0}}}, "views.v.workers", id="view"
        ),
        pytest.param({"actions": 12}, "actions", id="actions-not-a-list"),
        pytest.param({"actions": [["note"]]}, "actions.0", id="action-not-a-mapping"),
        pytest.param({"color_scheme": [1]}, "color_scheme", id="color-scheme"),
        pytest.param({"color_scheme": "sepia"}, "color_scheme", id="unknown-scheme"),
    ],
)
def test_loading_refuses_a_value_the_build_would(
    section: dict[str, Any], where: str
) -> None:
    """Refuse at load a `workers`, `actions` or `color_scheme` value the build would refuse."""
    with pytest.raises(ConfigurationError, match=re.escape(f"{where}: ")):
        validate_session([], {"session": "s", **section})


@pytest.mark.parametrize(
    ("section", "valid"),
    [
        pytest.param({"presenters": {"p": ENTRY}}, True, id="both"),
        pytest.param({"presenters": {"p": {"x": 1}}}, True, id="neither"),
        pytest.param(
            {"presenters": {"p": {"plugin_name": "redsun"}}}, False, id="name"
        ),
        pytest.param({"views": {"v": {"plugin_id": "log"}}}, False, id="id"),
        pytest.param(
            {"devices": {"d": {**ENTRY, "plugin_idd": "x"}}}, False, id="misspelled"
        ),
    ],
)
def test_the_schema_pairs_the_plugin_keys_as_loading_does(
    section: dict[str, Any], valid: bool
) -> None:
    """Refuse one plugin key without the other, and a misspelled one, in the schema."""
    document = {"session": "s", **section}
    if valid:
        jsonschema.validate(document, session_file_schema())
    else:
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(document, session_file_schema())


def test_the_manifest_schema_refuses_what_is_not_a_class_path() -> None:
    """Accept `module:ClassName` in the manifest schema, and refuse a dotted path."""
    schema = PluginManifest.model_json_schema()
    jsonschema.validate({"devices": {"motor": "mylab.devices:MyMotor"}}, schema)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"devices": {"motor": "mylab.devices.MyMotor"}}, schema)
