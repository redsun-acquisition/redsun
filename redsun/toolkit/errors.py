"""RedSun toolkit custom exceptions."""

__all__ = ["UnsupportedDeviceType"]


class UnsupportedDeviceType(Exception):
    """Raised when an unsupported device type is found in a specific engine."""

    def __init__(self, engine: str, dev_type: str) -> None:
        super().__init__()
        self.engine = engine
        self.dev_type = dev_type

    def __str__(self) -> str:
        """:meta-private:"""  # noqa: D400
        return "{} does not support '{}' models".format(self.engine, self.dev_type)
