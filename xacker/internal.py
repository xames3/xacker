"""Internal utility which executes commands on the CLI."""

import argparse
import os
import subprocess
import time
import typing as t

from .logger import get_logger

__all__ = [
    "configure_docker_remove",
    "configure_docker_run",
    "list_containers",
    "remove_containers_or_images",
    "run_container",
]

_daemon_wait: float = 20.0

_log = get_logger(__name__)


def _docker_is_not_running() -> int:
    """Check if the docker daemon is running or not."""
    _log.debug("Checking if the docker daemon is running...")
    return subprocess.run(["docker", "ps"], stderr=-3, stdout=-3).returncode


def _start_docker() -> None:
    """Start docker daemon if not running."""
    if _docker_is_not_running():
        _log.warning("Docker daemon is not running. Starting docker...")
        subprocess.run(["open", "--background", "-a", "Docker"])
        _log.info(
            "Docker daemon starting in the background, "
            f"expected start time {_daemon_wait} secs"
        )
        # TODO (xames3): This can be optimized to not wait implicitly.
        time.sleep(_daemon_wait)
    _log.info("Docker daemon is running...")


def _container_exists(name: str) -> int:
    """Check if the named container exists or not."""
    _log.info("Checking if the container exists...")
    docker_ps = subprocess.Popen(["docker", "ps", "-a"], stdout=-1)
    awk = subprocess.Popen(
        ["awk", "{if(NR>1) print $NF}"], stdin=docker_ps.stdout, stdout=-1
    )
    docker_ps.stdout.close()  # type: ignore
    return 1 if name in awk.communicate()[0].decode().splitlines() else 0


def run_container(argv: argparse.Namespace, options: list[str]) -> t.NoReturn:
    """Run docker containers on demand.

    This function uses the ``docker run`` command to spin a new
    container. The docker run command first creates a writeable container
    layer over the specified image, and then starts it using the specified
    command.

    Docker runs processes in isolated containers. A container is a
    process which runs on a host. The host may be local or remote. When
    an operator executes docker run, the container process that runs is
    isolated in that it has its own file system, its own networking, and
    its own isolated process tree separate from the host.

    We spin a docker container with some basic utilities in place like
    the hostname and working directory. However, these configurations can
    be overridden if needed.

    :param argv: ArgumentParser Namespaces.
    :param rest: Extra docker arguments which are not supported natively
        by xacker.

    .. versionchanged:: 2.0.0
        The argv parameter is now a Namespace object unlike before.

    .. versionchanged:: 2.0.0
        Function now checks if docker is running or not. If not, then
        start docker first.
    """
    if _docker_is_not_running():
        _start_docker()
    name = argv.name
    if _container_exists(name):
        _log.info(f"Container: {name} already exists! Starting now...")
        cmd = ["docker", "start", "-ia", name]
        os.execvp(cmd[0], cmd)
    if name is None:
        _log.info("Spawning a temporary container...")
        name = "--rm"
    else:
        name = f"--name {name}"
        _log.info(f"Spawning new container: {name[7:]}...")
    cmd = [
        "docker",
        "run",
        "-ti",
        *name.split(),
        "--hostname",
        argv.hostname,
        "--workdir",
        argv.workdir,
        *options,
        argv.image,
        argv.command,
    ]
    cmd = list(filter(None, cmd))
    _log.debug(f"Executing docker command: {' '.join(cmd)}")
    os.execvp(cmd[0], cmd)


def list_containers(_: argparse.Namespace, options: list[str]) -> t.NoReturn:
    """List containers as required.

    .. versionchanged:: 2.0.0
        Instead of giving warning, docker will start running if not
        actively running before.
    """
    if _docker_is_not_running():
        _start_docker()
    cmd = ["docker", "ps", "-a", *options]
    os.execvp(cmd[0], cmd)


def remove_containers_or_images(
    argv: argparse.Namespace, options: list[str]
) -> t.NoReturn:
    """Remove one of multiple containers or images from user's system.

    .. versionadded:: 2.0.0
        Added support for removing images and containers.
    """
    if _docker_is_not_running():
        _start_docker()
    if all([argv.container, argv.image]):
        _log.error("Can't remove containers and images simutaneously!")
        _log.warning(
            "Container(s) will be removed. For removing image(s) run: "
            f"xacker rm --image {' '.join(argv.image)}"
        )
    if argv.image:
        cmd = ["docker", "rmi", *argv.image, *options]
    if argv.container:
        cmd = ["docker", "rm", *argv.container, *options]
    os.execvp(cmd[0], cmd)


def configure_docker_run(
    parser: t.Union[argparse.ArgumentParser, argparse._ActionsContainer]
) -> None:
    """Parser for configuring docker run command.

    .. versionadded:: 2.0.0
        Image argument has default image of Python 3.10.

    .. versionchanged:: 2.0.0
        Help is deprecated from docker run.
    """
    parser.add_argument(
        "-c",
        "--command",
        help="Command to execute in the running container.",
        metavar="<command>",
    )
    parser.add_argument(
        "-n",
        "--name",
        help="Name for the container.",
        metavar="<name>",
    )
    parser.add_argument(
        "-w",
        "--workdir",
        default="/tmp/code",
        help="Working directory inside the container (Default: %(default)s).",
        metavar="<path>",
    )
    parser.add_argument(
        "--hostname",
        default="XAs-Docker-Container",
        help="Container host name (Default: %(default)s).",
        metavar="<hostname>",
    )
    parser.add_argument(
        "--image",
        help="Image to be used for creating the development container.",
        metavar="<image>",
    )


def configure_docker_remove(
    parser: t.Union[argparse.ArgumentParser, argparse._ActionsContainer]
) -> None:
    """Parser for configuring docker rm command.

    .. versionadded:: 2.0.0
        Added support for removing images and containers.
    """
    parser.add_argument(
        "-c",
        "--container",
        nargs="+",
        help=(
            "List of containers to be removed. Container has more "
            "precedence over images."
        ),
        metavar="<container>",
    )
    parser.add_argument(
        "-i",
        "--image",
        nargs="+",
        help=(
            "List of images to be removed. Container has more "
            "precedence over images"
        ),
        metavar="<image>",
    )
