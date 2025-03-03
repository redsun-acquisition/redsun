from attrs import define

@define(kw_only=True)
class BrokenModelInfo:
    plugin_name: str
    plugin_id: str


class BrokenModel:
    def __init__(self, name: str, model_info: BrokenModelInfo) -> None:
        self._name = name
        self._model_info = model_info
