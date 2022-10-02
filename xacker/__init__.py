"""\
xacker: A quick, easy and flexible development container thingy based on
Docker.

Basic Usage::

    $ xacker <command> [options] ...
or
    $ xacker --help

.. versionadded:: 1.0.0
    Added ability to spawn docker containers based on image and passed
    arguments. This allows user to start a container just by passing
    the docker parameter. The specifications of the container can be
    modified based on the command line arguments provided as inputs.

.. versioadded:: 2.0.0
    Added support for multiple subparsers to support different
    operations like listing containers and removing images/containers.

Author: Akshay Mestry (XAMES3) <xa@mes3.dev>
Last Update: October 02, 2022
"""

__version__ = "2.0.0"
