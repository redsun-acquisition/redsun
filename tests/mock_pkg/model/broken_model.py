from attrs import define
from sunflare.model import Model

@define(kw_only=True)
class BrokenModelInfo:
    plugin_name: str
    plugin_id: str


class BrokenModel:
    def __init__(self, name: str, model_info: BrokenModelInfo) -> None:
        self._name = name
        self._model_info = model_info

class BrokenInitModel(Model[BrokenModelInfo]):
    def __init__(self, name: str, model_info: BrokenModelInfo) -> None:
        super().__init__(name, model_info)
        raise ValueError("This model is broken")
