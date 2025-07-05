"""
Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""
import datetime
import pathlib

from PyQt6.QtCore import QThreadPool
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import QSystemTrayIcon, QApplication, QMenu
from zala.main_window import ZalaSelect

from lancet.consts import APP_LOGO_PATH, SCREENSHOT_ICON_PATH, EXIT_ICON_PATH, APP_NAME
from lancet.ocr import MangaOCRLauncher
from zala.screenshot import ZalaScreenshot


def make_output_file_path():
    return pathlib.Path.home() / "Pictures" / "Screenshots" / f"{datetime.datetime.now().isoformat()}.png"


class LancetSystemTray(QSystemTrayIcon):
    """
    System tray application containing all global actions
    """
    ocr_model: MangaOCRLauncher | None = None

    _scr: ZalaScreenshot
    _app: QApplication
    _sel: ZalaSelect | None = None

    def __init__(self, app: QApplication, parent=None):
        super().__init__(parent)
        self._app = app
        self._scr = ZalaScreenshot(app)

        # State trackers and configurations
        self.threadpool = QThreadPool.globalInstance()
        self.ocr_model = None
        # self.loadHotkeys()
        self.setIcon(QIcon(str(APP_LOGO_PATH)))
        # Menu
        menu = QMenu(parent)
        self.setContextMenu(menu)

        # Menu Actions
        menu.addAction(QIcon(str(SCREENSHOT_ICON_PATH)), "Make screenshot", self.make_screenshot)
        menu.addAction(QIcon(str(EXIT_ICON_PATH)), "Exit", self._app.quit)

    def make_screenshot(self) -> None:
        self._sel = ZalaSelect(self._scr.capture_screen())
        self._sel.window_closed.connect(self.process_select_result)
        self._sel.showFullScreen()

    def process_select_result(self, user_selection: QPixmap) -> None:
        if user_selection is None:
            self.showMessage(APP_NAME, "Selection aborted")
            return
        output_path = make_output_file_path()
        if user_selection.save(str(output_path)):
            self.showMessage(APP_NAME, f"Selection saved to {output_path}")
        else:
            self.showMessage(APP_NAME, f"Failed to save selection to {output_path}")
