from attrs import define
from sunflare.config import ModelInfo
from sunflare.model import Model

@define(kw_only=True)
class HiddenModelInfo(ModelInfo):
    ...

class HiddenModel(Model[HiddenModelInfo]):
    def __init__(self, name: str, model_info: HiddenModelInfo) -> None:
        super().__init__(name, model_info)
