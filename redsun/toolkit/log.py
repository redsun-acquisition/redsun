import logging
import logging.config
from typing import Protocol
from typing_extensions import override

__all__ = ["Loggable", "get_logger"]

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from typing import Any, Dict, Union

class ClassFormatter(logging.Formatter):
    """Custom formatter for logging messages with class name and user-defined ID."""

    STD_FORMAT = "[%(asctime)s][%(levelname)s]"

    def __init__(self, datefmt: str) -> None:
        super().__init__(datefmt=datefmt)

    @override
    def format(self, record: logging.LogRecord) -> str:
        fmt = self.STD_FORMAT
        message = []
        message.append(record.getMessage())
        record.message = " ".join(message)
        record.asctime = self.formatTime(record, self.datefmt)
        if "clsname" in record.__dict__:
            fmt += " [%(clsname)s"
            if "uid" in record.__dict__ and record.__dict__["uid"] is not None:
                fmt += " -> %(uid)s"
            fmt += "]"
        fmt += " %(message)s"
        if record.levelno >= logging.INFO:
            fmt += " (%(filename)s:%(lineno)d)"
        formatted = fmt % record.__dict__
        return formatted


# TODO: this should be moved to a json file
config = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"()": lambda: ClassFormatter(datefmt="%d-%m-%y | %H:%M:%S")}
    },
    "handlers": {
        "stdout": {
            "class": "logging.StreamHandler",
            "level": "DEBUG",
            "formatter": "simple",
            "stream": "ext://sys.stdout",
        }
    },
    "loggers": {
        "redsun": {"level": "DEBUG", "propagate": True, "handlers": ["stdout"]}
    },
}

# Set configuration
logging.config.dictConfig(config)

# Base logger for the entire system
logger = logging.getLogger("redsun")


class Loggable(Protocol):
    """ Protocol to extend log records with the class name and the user defined ID.\\
    Models and controllers can inherit from this class to have a consistent log format.\\
    All methods allow to forward extra arguments to the logger calls as documented in the `logging` module.

    Properties
    ----------
    name : str
        The user defined ID of the instance.
        This property should be provided by the models inheriting from this class.
    """

    def _extend(self, **kwargs: "Any") -> "Dict[str, Any]":
        """Enrich kwargs with class name and user-defined ID.
        :meta-private:
        """
        kwargs["extra"] = {
            **kwargs.get("extra", {}),
            "clsname": self.__clsname__,
            "uid": self.name,
        }
        return kwargs

    def info(self, msg: str, *args: "Any", **kwargs: "Any") -> None:
        """Log an info message in the core logger

        Parameters
        ----------
        msg : str
            String to log.
        *args : Any
            Additional positional arguments for `logging.Logger.info`.
        **kwargs : Any
            Additional keyword arguments for `logging.Logger.info`.
        """
        self._extend(**kwargs)
        logger.info(msg, *args, **kwargs)

    def debug(self, msg: str, *args: "Any", **kwargs: "Any") -> None:
        """Log a debug message in the core logger

        Parameters
        ----------
        msg : str
            String to log.
        *args : Any
            Additional positional arguments for `logging.Logger.debug`.
        **kwargs : Any
            Additional keyword arguments for `logging.Logger.debug`.
        """
        self._extend(**kwargs)
        logger.debug(msg, *args, **kwargs)

    def warning(self, msg: str, *args: "Any", **kwargs: "Any") -> None:
        """Log a warning message in the core logger

        Parameters
        ----------
        msg : str
            String to log.
        *args : Any
            Additional positional arguments for `logging.Logger.warning`.
        **kwargs : Any
            Additional keyword arguments for `logging.Logger.warning`.
        """
        self._extend(**kwargs)
        logger.warning(msg, *args, **kwargs)

    def error(self, msg: str, *args: "Any", **kwargs: "Any") -> None:
        """Log an error. message in the core logger

        Parameters
        ----------
        msg : str
            String to log.
        *args : Any
            Additional positional arguments for `logging.Logger.error`.
        **kwargs : Any
            Additional keyword arguments for `logging.Logger.error`.
        """
        self._extend(**kwargs)
        logger.error(msg, *args, **kwargs)

    def critical(self, msg: str, *args: "Any", **kwargs: "Any") -> None:
        """Log a critical message in the core logger

        Parameters
        ----------
        msg : str
            String to log.
        *args : Any
            Additional positional arguments for `logging.Logger.critical`.
        **kwargs : Any
            Additional keyword arguments for `logging.Logger.critical`.
        """
        self._extend(**kwargs)
        logger.critical(msg, *args, **kwargs)

    def exception(self, msg: str, *args: "Any", **kwargs: "Any") -> None:
        """Log an exception message in the core logger

        Parameters
        ----------
        *args : Any
            Additional positional arguments for `logging.Logger.exception`.
        **kwargs : Any
            Additional keyword arguments for `logging.Logger.exception`.
        """
        self._extend(**kwargs)
        logger.exception(msg, *args, **kwargs)

    @property
    def __clsname__(self) -> str:
        # Private property, should not be
        # accessed by the user
        return self.__class__.__name__

    @property
    def name(self) -> "Union[str, None]":
        # This property should be implemented by
        # all model and controller classes by default
        return None


def get_logger() -> logging.Logger:
    """Returns the core logger.

    Returns
    -------
    logging.Logger
        The core logger instance.
    """
    return logger
