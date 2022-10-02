"""\
xacker.main: Module responsible for interacting with xacker over command
line.

.. versionadded:: 2.0.0
"""

import argparse
import os
import shutil
import sys
import textwrap
import typing as t

from xacker import __version__ as version
from xacker.internal import configure_docker_remove
from xacker.internal import configure_docker_run
from xacker.internal import list_containers
from xacker.internal import remove_containers_or_images
from xacker.internal import run_container
from xacker.logger import configure_logger
from xacker.logger import init

_terminal_width: int = shutil.get_terminal_size().columns - 2
_terminal_width = _terminal_width if _terminal_width < 79 else 79


class _HelpFormatter(argparse.RawTextHelpFormatter):
    """Custom formatter for customizing command layout, usage message
    and wrapping lines.

    This class overrides the default behavior and adds custom usage
    message template. Also it sets a soft limit for wrapping the help
    and description strings.
    """

    def __init__(
        self,
        prog: str,
        indent_increment: int = 2,
        max_help_position: int = 50,
        width: t.Optional[int] = None,
    ) -> None:
        """Update the ``max_help_position`` to accomodate metavar."""
        super().__init__(prog, indent_increment, max_help_position, width)

    # See https://stackoverflow.com/a/35848313/14316408 for customizing
    # the usage section when looking for help.
    def add_usage(
        self,
        usage: t.Optional[str],
        actions: t.Iterable[argparse.Action],
        groups: t.Iterable[argparse._ArgumentGroup],
        prefix: t.Optional[str] = None,
    ) -> None:
        """Capitalize the usage text."""
        if prefix is None:
            sys.stdout.write("\n")
            prefix = "Usage:\n "
        return super().add_usage(usage, actions, groups, prefix)

    # See https://stackoverflow.com/a/35925919/14316408 for adding the
    # line wrapping logic for the description.
    def _split_lines(self, text: str, _: int) -> list[str]:
        """Unwrap the lines to width of the terminal."""
        text = self._whitespace_matcher.sub(" ", text).strip()
        return textwrap.wrap(text, _terminal_width)

    # See https://stackoverflow.com/a/13429281/14316408 for hiding the
    # metavar is sub-command listing.
    def _format_action(self, action: argparse.Action) -> str:
        """Hide Metavar in command listing."""
        parts = super()._format_action(action)
        if action.nargs == argparse.PARSER:
            parts = "\n".join(parts.splitlines()[1:])
        return parts

    # See https://stackoverflow.com/a/23941599/14316408 for disabling
    # the metavar for short options.
    def _format_action_invocation(self, action: argparse.Action) -> str:
        """Disable Metavar for short options.

        .. versionadded:: 2.0.0
        """
        if not action.option_strings:
            (metavar,) = self._metavar_formatter(action, action.dest)(1)
            return metavar
        parts: list[str] = []
        if action.nargs == 0:
            parts.extend(action.option_strings)
        else:
            default = action.dest.upper()
            args_string = self._format_args(action, default)
            for option_string in action.option_strings:
                parts.append(f"{option_string}")
            parts[-1] += f" {args_string}"
        return ", ".join(parts)


def _get_prog():
    """Get program name.

    .. versionadded:: 2.0.0
        Added support for programmatically fetching the program name.
        The implementation is replicated from ``pip`` module.
    """
    try:
        prog = os.path.basename(sys.argv[0])
        if prog in ("__main__.py", "-c"):
            return f"{sys.executable} -m xacker"
        else:
            return prog
    except (AttributeError, TypeError, IndexError):
        pass
    return "xacker"


def _create_subparser(
    subparsers: argparse._SubParsersAction,
    parents: list[argparse.ArgumentParser],
    command: str,
    title: str,
    usage: str,
    help: str,
    description: str,
    callback: t.Callable[[argparse.Namespace, list[str]], t.NoReturn],
    configure: t.Callable[[argparse.ArgumentParser], None] = None,
) -> None:
    """Create subparser object."""
    parser = subparsers.add_parser(
        command,
        usage=usage,
        formatter_class=_HelpFormatter,
        conflict_handler="resolve",
        description=description,
        help=help,
        parents=parents,
        add_help=False,
    )
    if configure:
        configure(parser)
    parser._optionals.title = title
    parser.set_defaults(function=callback)


def _configure_general(
    parser: t.Union[argparse.ArgumentParser, argparse._ActionsContainer]
) -> None:
    """Add general options to the parser object.

    .. versionadded:: 2.0.0
        General options section is now a seperate parser object.
    """
    parser = parser.add_argument_group("General Options")
    parser.add_argument(
        "-h",
        "--help",
        action="help",
        default=argparse.SUPPRESS,
        help="Show this help message.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help=(
            "Increase the logging verbosity. This option is additive, and "
            "can be used twice. The logging verbosity can be overridden by "
            "setting XACKER_LOGGING_LEVEL (corresponding to "
            "DEBUG, INFO, WARNING, ERROR and CRITICAL logging levels)."
        ),
    )
    # See https://stackoverflow.com/a/8521644/812183 for adding version
    # specific argument to the parser.
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"xacker v{version}",
        help="Show xacker's installed version and exit.",
    )


def _create_main_parser() -> argparse.ArgumentParser:
    """Create and return the main parser object for xacker's CLI.

    It powers the main argument parser for the xacker module.

    :returns: ArgumentParser object which stores all the properties of
        the main argument parser.

    .. versionadded:: 2.0.0
        Added support for main parent parser to parse command line
        arguments.
    """
    prog = _get_prog()
    main_parser = argparse.ArgumentParser(
        prog=prog,
        usage=f"{prog} <command> [options]",
        formatter_class=_HelpFormatter,
        conflict_handler="resolve",
        add_help=False,
        description=(
            "xacker: A quick, easy and flexible development container "
            "thingy based on Docker."
        ),
        epilog=(
            'For specific information about a particular command, run "'
            'xacker <command> -h".\nRead complete documentation at: '
            "https://github.com/xames3/xacker\n\nCopyright (c) 2022 "
            "Akshay Mestry (XAMES3). All rights reserved."
        ),
    )
    main_parser._positionals.title = "Commands"
    parent_parser = argparse.ArgumentParser(add_help=False)
    for parser in (main_parser, parent_parser):
        _configure_general(parser)
        configure_logger(parser)
    subparsers = main_parser.add_subparsers(prog=prog)
    _create_subparser(
        subparsers=subparsers,
        parents=[parent_parser],
        command="run",
        title="Run Options",
        usage=(
            f"{prog} run [options] --image <image> --name <name> ...\n "
            f"{prog} run [options] --image <image> ..."
        ),
        description=(
            "Run docker containers.\n\nThis command performs ``docker run`` "
            "and/or ``docker start`` under the hood to run a\nnew container "
            "or start an existing one respectively. The started containers "
            "have attached\nand open STDIN, STDOUT or STDERR by default along "
            "with pseudo-TTY allocated for the\nuser's interaction."
        ),
        help="Run docker containers.",
        configure=configure_docker_run,
        callback=run_container,
    )
    _create_subparser(
        subparsers=subparsers,
        parents=[parent_parser],
        command="ls",
        title="List Options",
        usage=f"{prog} ls [options] ...",
        description=(
            "List all containers.\n\nThis command performs ``docker ps -a`` "
            "under the hood to show all the containers which are\navailable "
            "at the user's disposal."
        ),
        help="List docker containers.",
        callback=list_containers,
    )
    _create_subparser(
        subparsers=subparsers,
        parents=[parent_parser],
        command="rm",
        title="Remove Options",
        usage=(
            f"{prog} rm [options] --container <container1> <container2> ...\n "
            f"{prog} rm [options] --image <image1> ..."
        ),
        description=(
            "Remove one or multiple images or containers.\n\nThis command "
            "performs ``docker rm`` under the hood to remove the images "
            "and containers\nwhich are available on the user's system."
        ),
        help="Remove docker containers.",
        configure=configure_docker_remove,
        callback=remove_containers_or_images,
    )
    return main_parser


def main() -> int:
    """Primary application entrypoint.

    This function is called at the entrypoint, meaning that when the
    user runs this function, it will display the CLI for xacker.

    .. versionadded:: 2.0.0
    """
    parser = _create_main_parser()
    _args, _rest = parser.parse_known_args()
    _log_options = {
        "level": _args.verbose or _args.level,
        "fmt": _args.format,
        "datefmt": _args.datefmt,
        "color": _args.no_color,
        "filename": _args.log,
        "max_bytes": _args.max_bytes,
        "backup_count": _args.backup_count,
        "skip_logging": _args.no_output,
    }
    _log = init(**_log_options)
    _log.debug(f"Python version: {sys.version}")
    _log.debug(f"Start command for xacker: {' '.join(sys.argv)}")
    if hasattr(_args, "function"):
        try:
            _args.function(_args, _rest)
        except UnboundLocalError:
            _log.error("No arguments passed to the command!")
    else:
        parser.print_help()
    return 0
