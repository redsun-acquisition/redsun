from redsun.controller.factory import get_available_engines
from redsun.engine.exengine import ExEngineHandler

def test_handlers_dict() -> None:
    """Test the content of the handlers dictionary."""
    engines = get_available_engines()
    assert len(engines) > 0
    assert "exengine" in engines
    assert engines["exengine"] == ExEngineHandler
