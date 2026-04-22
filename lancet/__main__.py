# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
import pathlib
import shutil
import socket
import sys
from collections.abc import Iterator
from contextlib import contextmanager

from loguru import logger
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from lancet.config import Config
from lancet.consts import APP_LOGO_PATH, APP_NAME, DESKTOP_FILE, IS_MAC, IS_WIN
from lancet.exceptions import PortAlreadyInUseError
from lancet.system_tray import LancetSystemTray


def drop_launch_shortcut() -> None:
    """
    Create desktop shortcut and icon files if they don't exist.
    """
    if IS_MAC or IS_WIN:
        return

    # Save desktop shortcut.
    user_file = pathlib.Path.home().joinpath(f".local/share/applications/{DESKTOP_FILE.name}")
    system_file = pathlib.Path(f"/usr/share/applications/{DESKTOP_FILE.name}")

    if not (system_file.is_file() or user_file.is_file()):
        try:
            user_file.write_text(
                DESKTOP_FILE.read_text(encoding="utf-8").replace("{{ICON}}", APP_NAME.lower()),
                encoding="utf-8",
            )
        except FileNotFoundError:
            pass

    # Save icon file.
    user_icon_file = pathlib.Path.home().joinpath(f".local/share/icons/{APP_NAME.lower()}{APP_LOGO_PATH.suffix}")
    if not user_icon_file.is_file():
        try:
            shutil.copyfile(APP_LOGO_PATH, user_icon_file)
        except OSError:
            pass


@contextmanager
def singleton_instance(cfg: Config) -> Iterator[socket.socket]:
    """
    Context manager that ensures only one instance of the application is running.
    Uses socket binding to a specific port to ensure singleton behavior.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        # Bind to a specific port (choose an unused one)
        try:
            sock.bind(("127.0.0.1", cfg.bind_port))
        except OSError as ex:
            raise PortAlreadyInUseError("Another instance of this program is already running") from ex
        yield sock
    finally:
        # Code to release resource, e.g.:
        sock.close()


def run_program(cfg: Config) -> None:
    """
    Initialize and run the Lancet system tray application.
    """

    drop_launch_shortcut()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(QIcon(str(APP_LOGO_PATH)))
    app.setQuitOnLastWindowClosed(False)

    widget = LancetSystemTray(app, cfg)
    widget.show()

    sys.exit(app.exec())


def main() -> None:
    """
    Main entry point for the Lancet application.
    Reads configuration, ensures singleton instance, and runs the program.
    """
    cfg = Config.read_from_file()
    if not cfg.file_exists():
        cfg.save_to_file()

    try:
        with singleton_instance(cfg):
            run_program(cfg)
    except PortAlreadyInUseError as ex:
        logger.warning(str(ex))


if __name__ == "__main__":
    main()
