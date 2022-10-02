"""Log xacker messages.

This module defines the functions and classes that make up xacker's
versatile event logging system.

The main advantage of having a logging API is that it allows all modules
to participate in logging. It provides the essential abstractions for
configuring the system's default logging capabilities. Object from the
logging module are monkey-patched to do this.

This module is also in charge of displaying color on the terminal to
indicate the severity of logging levels.
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
import types
import typing as t
from logging.handlers import RotatingFileHandler

__all__ = ["configure_logger", "get_logger", "init"]

_iso8601: str = "%Y-%m-%dT%H:%M:%SZ"
_logger_name: str = "xacker.main"
_logfile: str = os.path.join(os.path.expanduser("~"), ".xacker", "session.log")
_verbosity_level_map: t.Dict[int, int] = {
    0: 30,
    1: 20,
    2: 10,
}
_logging_level_map: t.Dict[str, int] = {
    "TRACE": 60,
    "FATAL": 50,
    "CRITICAL": 50,
    "ERROR": 40,
    "WARN": 30,
    "WARNING": 30,
    "INFO": 20,
    "DEBUG": 10,
    "NOTSET": 00,
}

_ansi_escape_re = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def _setup_logs_dir(
    override: t.Union[bool, str], path: t.Optional[str]
) -> t.Optional[str]:
    """Create a log directory and log all stdin-stdout I/O to it.

    For redundancy and history*, the logs are stored by default in the
    ``$HOME/.xacker`` directory. This function will create the directory
    if it has been deleted or if it does not exist for some reason.

    If you don't want this behavior, use the ``XACKER_SKIP_LOGGING``
    environment variable to disable logging.

    :param override: If this is set to True, it will override logging.
    :param path: The path to the log file that will be used to establish
        the logging parent directory.
    :returns: Path if logging is required.
    """
    if override or override in ("TRUE", "True", "true", "t"):
        return None
    if path is None:
        path = _logfile
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


def _skip_output_logs(choice: bool) -> bool:
    """Return whether to output logs to a file.

    This function only has effect if the ``XACKER_SKIP_LOGGING``
    environment variable is set to True. It will continue to report
    output to the file if nothing is set.

    :param choice: Boolean flag to skip logs.
    :returns: Status whether to log file or not.
    """
    _skip = os.getenv("XACKER_SKIP_LOGGING")
    # This ensures that only the True values are considered as valid
    # choices. This is required or else any non-empty string would be
    # considered as True and the loop might accidentally execute.
    if (_skip and _skip in ("TRUE", "True", "true", "t")) or choice:
        return True
    return False


def _select_log_level(level: t.Union[int, str]) -> int:
    """Select the logging level to use.

    The ``XACKER_LOGGING_LEVEL`` environment variable can be used to
    alter the logging level. The verbosity counter will be overridden if
    the variable is set to a proper log level. If nothing is specified,
    the verbosity setting will be used for logging.

    Higher the counter, lower the logging level.

    :param level: Verbosity counter value or the implicit logging level.
    :returns: Logging level.
    """
    _level = os.getenv("XACKER_LOGGING_LEVEL")
    if _level:
        return _logging_level_map[_level]
    if isinstance(level, str):
        return _logging_level_map[level]  # This if block is unnecessary!
    if level in (00, 10, 20, 30, 40, 50, 60):
        return level
    level = min(level, 2)  # This enables users to do -vv
    return _verbosity_level_map[level]


def _use_color(choice: bool) -> str:
    """Return log format based on the choice.

    If choice is True, colored log format is returned else non-colored
    format is returned.

    :param choice: Boolean value to allow colored logs.
    :returns: Colored or non-colored log format based on choice.
    """
    if choice:
        return (
            "%(gray)s%(asctime)s %(color)s%(levelname)8s%(reset)s "
            "%(gray)s%(stack)s:%(lineno)d%(reset)s : %(message)s"
        )
    return "%(asctime)s %(levelname)8s %(stack)s:%(lineno)d : %(message)s"


class _Formatter(logging.Formatter):
    """ANSI color scheme formatter.

    This class formats the ``record.pathname`` and ``record.exc_info``
    attributes to generate an uniform and clear log message. The class
    adds gray hues to the log's metadata and colorizes the levels.

    :param fmt: Format for the log message.
    :param datefmt: Format for the log datetime.
    :var _ansi_attrs: Attributes to be added to the log record.
    :var _ansi_hue_map: Mapping of hues for different logging levels.
    """

    _ansi_attrs: t.Tuple[str, ...] = "color", "gray", "reset"
    # See https://stackoverflow.com/a/14693789/14316408 for the RegEx
    # logic behind the ANSI escape sequence.
    _ansi_hue_map: t.Dict[int, str] = {
        90: "\x1b[38;5;242m",
        60: "\x1b[38;5;128m",
        50: "\x1b[38;5;197m",
        40: "\x1b[38;5;204m",
        30: "\x1b[38;5;215m",
        20: "\x1b[38;5;41m",
        10: "\x1b[38;5;14m",
        00: "\x1b[0m",
    }

    def __init__(self, fmt: str, datefmt: str) -> None:
        """Initialize the formatter with suitable formats."""
        self.fmt = fmt
        self.datefmt = datefmt

    def _colorize(self, record: logging.LogRecord) -> None:
        """Add colors to the logging levels by manipulating log records.

        This approach is on the cutting edge because it modifies the
        record object in real time. This has the potential to be a
        disadvantage. We verify if the logging stream is a TTY interface
        or not to avoid memory leaks. If we are certain that the stream
        is a TTY, we alter the object.

        As a result, when writing to a file, this method avoids the
        record from containing unreadable ANSI characters.

        :param record: Logged event's instance.
        """
        # The same could have been done using the ``hasattr()`` too.
        # This ``isatty`` is a special attribute which is injected by
        # the ``xacker.logger._StreamHandler()`` class.
        if getattr(record, "isatty", False):
            hue_map = zip(("color", "gray", "reset"), (record.levelno, 90, 0))
            for hue, level in hue_map:
                setattr(record, hue, self._ansi_hue_map[level])
        else:
            for attr in self._ansi_attrs:
                setattr(record, attr, "")

    def _decolorize(self, record: logging.LogRecord) -> None:
        """Remove ``color``, ``gray`` and ``reset`` attributes from the
        log record.

        This method is opposite of ``colorize()`` of the same class.
        It prevents the record from writing un-readable ANSI characters
        to a non-TTY interface.

        :param record: Logged event's instance.
        """
        for attr in self._ansi_attrs:
            delattr(record, attr)

    def formatException(
        self,
        ei: t.Union[
            t.Tuple[type, BaseException, t.Optional[types.TracebackType]],
            t.Tuple[None, ...],
        ],
    ) -> str:
        r"""Format exception information as text.

        This implementation does not work directly. The log formatter
        from the standard library is required. The parent class creates
        an output string with ``\n`` which needs to be truncated and
        this method does this well.

        :param ei: Information about the captured exception.
        :returns: Formatted exception string.
        """
        func, lineno = "<module>", 0
        cls_, msg, tbk = ei
        if tbk:
            func, lineno = tbk.tb_frame.f_code.co_name, tbk.tb_lineno
        func = "on" if func in ("<lambda>", "<module>") else f"in {func}() on"
        return f"{cls_.__name__ if cls_ else cls_}: {msg} line {lineno}"

    @staticmethod
    def _stack(path: str, func: str) -> str:
        """Format path and function as stack.

        :param path: Path of the module which is logging the event.
        :param func: Callable object's name.
        :returns: Spring-boot style formatted path, well kinda...

        .. note::

            If called from a module, the base path of the module would
            be used else "shell" would be returned for the interpreter
            (stdin) based inputs.

        """
        if path == "<stdin>":
            return "shell"  # Should not return this rightaway...
        if os.name == "nt":
            path = os.path.splitdrive(path)[1]
        # NOTE: This presumes we work through a virtual environment.
        # This is a safe assumption as we peruse through the site-
        # packages. In case, this is not running via the virtualenv, we
        # might get a different result.
        abspath = "site-packages" if "site-packages" in path else os.getcwd()
        path = path.split(abspath)[-1]
        path = path.replace(os.path.sep, ".")[path[0] != ":" : -3]
        if func not in ("<module>", "<lambda>"):
            path += f".{func}"
        return path

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as text.

        If any exception is captured then it is formatted using the
        ``formatException()`` and replaced with the original message.

        :param record: Logged event's instance.
        :returns: Captured and formatted output log message.
        """
        # Update the pathname and the invoking function name using the
        # stack. This stack will be set as a record attribute which will
        # allow us to use the %(stack)s placeholder in the log format.
        setattr(record, "stack", self._stack(record.pathname, record.funcName))
        if record.exc_info:
            record.msg = self.formatException(record.exc_info)
            record.exc_info = record.exc_text = None
        self._colorize(record)
        msg = logging.Formatter(self.fmt, self.datefmt).format(record)
        # Escape the ANSI sequence here as this will render the colors
        # on the TTY but won't add them to the non-TTY interfaces, for
        # example, log file.
        record.msg = _ansi_escape_re.sub("", str(record.msg))
        self._decolorize(record)
        return msg


class _StreamHandler(logging.StreamHandler):  # type: ignore
    """A StreamHandler derivative which adds an inspection of a TTY
    interface to the stream.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Add hint if the specified stream is a TTY.

        The ``hint`` here, means the boolean specification as this
        attribute helps to identify a stream's interface. This solves a
        major problem when printing un-readable ANSI sequences to a
        non-TTY interface.

        :param record: Logged event's instance.
        :returns: Formatted string for the output stream.
        """
        if hasattr(self.stream, "isatty"):
            try:
                setattr(record, "isatty", self.stream.isatty())
            except ValueError:
                setattr(record, "isatty", False)
        else:
            setattr(record, "isatty", False)
        strict = super().format(record)
        delattr(record, "isatty")
        return strict


def get_logger(module: str) -> logging.Logger:
    """Return logger instance.

    This function is supposed to be used by the modules for logging.
    The logger generated by this function is a child which reports logs
    back to the parent logger defined by the ``xacker.logger.init()``.

    :param module: Module to be logged.
    :returns: Logger instance.
    """
    return logging.getLogger(_logger_name).getChild(module)


def init(
    name: str = _logger_name,
    level: int = logging.INFO,
    fmt: t.Optional[str] = None,
    datefmt: str = _iso8601,
    color: bool = True,
    filename: t.Optional[str] = None,
    max_bytes: int = 10_000_000,
    backup_count: int = 10,
    encoding: t.Optional[str] = None,
    filemode: str = "a",
    skip_logging: bool = False,
    handlers: t.Optional[list[logging.Handler]] = None,
    stream: t.Optional[t.IO[str]] = sys.stderr,
    capture_warnings: bool = True,
) -> logging.Logger:
    """Initialize an application level logger.

    This function initializes a logger with default configurations for
    the logging system.

    If any handlers are provided as part of input, the function
    overrides the default behaviour in favour of the provided handler.
    It is a convenience function intended for use by simple applications
    to do one-shot configuration.

    :param name: Name for the logger, defaults to ``xacker.main``.
    :param level: Minimum logging level of the event, defaults to INFO.
    :param fmt: Format for the log message, defaults to None.
    :param datefmt: Format for the log datetime, defaults to ``ISO8601``
        format.
    :param color: Boolean option to whether display colored log outputs
        on the terminal or not, defaults to True.
    :param filename: Log file's absolute path, defaults to None.
    :param max_bytes: Maximum size in bytes after which the rollover
        should happen, defaults to 10 MB.
    :param backup_count: Maximum number of files to archive before
        discarding, defaults to 10.
    :param encoding: Platform-dependent encoding for the file, defaults
        to None.
    :param filemode: Mode in which the file needs to be opened, defaults
        to append ``a`` mode.
    :param skip_logging: Boolean option to whether skip the logging
        process, defaults to False.
    :param handlers: List of various logging handlers to use, defaults
        to None.
    :param stream: IO stream, defaults to ``sys.stderr``.
    :param capture_warnings: Boolean option to whether capture the
        warnings while logging, defaults to True.
    :returns: Configured logger instance.
    """
    logger = logging.getLogger(name)
    level = _select_log_level(level)
    logger.setLevel(level)
    if handlers is None:
        handlers = []
    for handler in logger.handlers:
        logger.removeHandler(handler)
        handler.close()
    if not logger.handlers:
        if fmt is None:
            fmt = _use_color(color)
        formatter = _Formatter(fmt, datefmt)
        stream_handler = _StreamHandler(stream)
        handlers.append(stream_handler)  # type: ignore
        if not _skip_output_logs(skip_logging):
            filename = _setup_logs_dir(skip_logging, filename)
            if filename:
                file_handler = RotatingFileHandler(
                    filename, filemode, max_bytes, backup_count, encoding
                )
                handlers.append(file_handler)
        for handler in handlers:
            logger.addHandler(handler)
            handler.setFormatter(formatter)
    logging.captureWarnings(capture_warnings)
    return logger


def configure_logger(
    parser: t.Union[argparse.ArgumentParser, argparse._ActionsContainer]
) -> None:
    """Parser for configuring the logger."""
    logger = parser.add_argument_group("Logging Options")
    logger.add_argument(
        "--log",
        default=_logfile,
        help=(
            "Path for logging and maintaining a historical log "
            "(Default: %(default)s)."
        ),
        metavar="<path>",
    )
    logger.add_argument(
        "-l",
        "--level",
        default=logging.INFO,
        help=(
            "Minimum logging level for the message (Default: %(default)s). "
            "The logging level can be overridden by setting the environment "
            "variable XACKER_LOGGING_LEVEL (corresponding to DEBUG, INFO, "
            "WARNING, ERROR and CRITICAL logging levels)."
        ),
        metavar="<level>",
        type=int,
    )
    logger.add_argument(
        "-b",
        "--max-bytes",
        default=10_000_000,
        help="Output log file size in bytes (Default: %(default)s).",
        metavar="<bytes>",
        type=int,
    )
    logger.add_argument(
        "--backup-count",
        default=10,
        help=(
            "Maximum number of files to archive before discarding "
            "(Default: %(default)s)."
        ),
        metavar="<count>",
        type=int,
    )
    logger.add_argument(
        "--format",
        help="Logging message string format.",
        metavar="<format>",
    )
    logger.add_argument(
        "--datefmt",
        default=_iso8601,
        help="Logging message datetime format (Default: %(default)s).",
        metavar="<format>",
    )
    logger.add_argument(
        "--no-output",
        action="store_true",
        help=(
            "Skips logging the I/O from stdin, stdout and stderr to the "
            "log file. This behavior can be overridden by setting the "
            "environment variable XACKER_SKIP_LOGGING to TRUE. If this is "
            "set, it will carry more precedence."
        ),
    )
    logger.add_argument(
        "--no-color",
        action="store_false",
        help="Suppress colored output.",
    )
