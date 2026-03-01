# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
import pathlib
import shutil
import sys

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from lancet.consts import APP_LOGO_PATH, APP_NAME, DESKTOP_FILE, IS_MAC, IS_WIN
from lancet.system_tray import LancetSystemTray


def drop_launch_shortcut() -> None:
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


def main() -> None:
    """Initialize and run the Lancet system tray application."""
    drop_launch_shortcut()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(QIcon(str(APP_LOGO_PATH)))
    app.setQuitOnLastWindowClosed(False)

    widget = LancetSystemTray(app)

    widget.show()
    # widget.loadModel()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
