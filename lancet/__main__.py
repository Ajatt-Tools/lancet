"""
Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""

import sys

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from lancet.system_tray import LancetSystemTray
from lancet.consts import APP_LOGO_PATH, APP_NAME


def main() -> None:
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
