# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
import sys

import fire
from loguru import logger

from lancet.cli import CLI, log_dependency_versions, run_program, setup_frozen_binary
from lancet.config import read_config_file
from lancet.exceptions import PortAlreadyInUseError
from lancet.ipc.server import IpcServer


def main() -> None:
    """
    Main entry point for the Lancet application.
    Reads configuration, ensures singleton instance, and runs the program.
    """
    setup_frozen_binary()
    log_dependency_versions()

    res = read_config_file()
    if res.error:
        # log the error and continue.
        logger.error(res.error)

    if not res.cfg.file_exists():
        res.cfg.save_to_file()

    if sys.argv[1:]:
        fire.Fire(CLI(res.cfg))
        return

    try:
        with IpcServer(res.cfg) as ipc:
            run_program(res, ipc)
    except PortAlreadyInUseError as ex:
        logger.warning(str(ex))


if __name__ == "__main__":
    main()
