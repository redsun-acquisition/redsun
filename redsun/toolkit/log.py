import inspect
import logging
import weakref
from typing import Optional, Union, List

# Base logger for the entire system
core_logger = logging.getLogger('redsun')
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s %(message)s')

# Dictionary to keep weak references to logger objects
loggers = weakref.WeakValueDictionary()

class RedSunLogger(logging.LoggerAdapter):
    """ A custom LoggerAdapter that allows dynamically injecting prefixes like plugin name and class name into log messages.

    Parameters
    ----------
    logger : logging.Logger
        Logger object.

    prefixes : List
        A list of prefixes such as plugin name and class name.
    
    reference : weakref.ReferenceType
        A weak reference to the object using the logger.
    """
    def __init__(self, logger: logging.Logger, prefixes: List, reference: weakref.ReferenceType):
        super().__init__(logger, {})
        self.prefixes = prefixes  # A list of prefixes such as plugin name and class name
        self.reference = reference  # A weak reference to the object using the logger

    def process(self, msg, kwargs):
        """
        Processes the log message by prepending the plugin and class names to the message.

        Parameters
        ----------
        msg : str
            The original log message.
        kwargs : dict
            Additional keyword arguments passed to the logger call.

        Returns
        -------
        tuple
            The processed log message and kwargs.
        """
        processedPrefixes = []
        for prefix in self.prefixes:
            if callable(prefix):
                try:
                    processedPrefixes.append(prefix(self.reference()))  # Use callable to retrieve class name
                except Exception:
                    pass  # If the object is garbage collected, we pass
            else:
                processedPrefixes.append(prefix)  # Otherwise, directly use the static value

        # Format the message with the prefixes
        processedMsg = f'[{" -> ".join(processedPrefixes)}] {msg}'
        return processedMsg, kwargs


def setup_logger(obj: Union[object, str], *, instance_name: Optional[str] = None, inherit_parent: bool = False):
    """
    Initializes a logger for the specified object (class, object, or string).

    Parameters
    ----------
    obj : object or str
        The object or class for which to initialize the logger.
    name : str, optional
        An additional name to include in the logger (for instance-specific loggers).
    inherit_parent : bool, optional
        If True, attempts to inherit the logger from a parent class or object.

    Returns
    -------
    LoggerAdapter
        A customized logger adapter for the object or class.
    """
    logger = None

    # If inherit_parent is True, look for a logger from a parent object in the call stack
    if inherit_parent:
        for frameInfo in inspect.stack():
            frameLocals = frameInfo[0].f_locals
            if 'self' not in frameLocals:
                continue

            parent = frameLocals['self']
            parentRef = weakref.ref(parent)
            if parentRef not in loggers:
                continue

            logger = loggers[parentRef]
            break

    if logger is None:
        # Create a new logger
        if inspect.isclass(obj):
            obj_name = obj.__name__  # If it's a class, use its name
            reference = weakref.ref(obj)
        elif isinstance(obj, str):
            obj_name = obj  # If it's a string, treat it as a static name (e.g., for plugins)
            reference = None
        else:
            obj_name = obj.__class__.__name__  # For objects, use the class name
            reference = weakref.ref(obj)

        # Prefixes include the plugin name (obj_name) and optionally the name of the instance
        prefixes = [obj_name, instance_name] if instance_name else [obj_name]
        logger = RedSunLogger(core_logger, prefixes, reference)

        # Save the logger in the weak reference dictionary if it's tied to an object
        if reference is not None:
            loggers[reference] = logger

    return logger