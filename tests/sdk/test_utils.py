from __future__ import annotations

import pytest

from redsun.utils.descriptors import parse_key, parse_map_key


def test_parse_key_round_trip() -> None:
    assert parse_key("det-roi-x") == ("det", "roi-x")
    with pytest.raises(ValueError, match="does not conform"):
        parse_key("nohyphen")


def test_parse_map_key() -> None:
    assert parse_map_key("stage-axis-x", "axis") == ("stage", "axis", "x")
    with pytest.raises(ValueError, match="does not conform"):
        parse_map_key("stage-x", "axis")
    with pytest.raises(ValueError, match="does not conform"):
        parse_map_key("stage-motor-x", "axis")
