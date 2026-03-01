# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import datetime
import pathlib
import signal

from PyQt6.QtCore import QThreadPool
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QSystemTrayIcon, QApplication, QMenu
from loguru import logger
from zala.main_window import ZalaSelect, UserSelectionResult
from zala.screenshot import ZalaScreenshot

from lancet.config import Config, OcrDestination
from lancet.consts import APP_LOGO_PATH, SCREENSHOT_ICON_PATH, EXIT_ICON_PATH, OCR_ICON_PATH
from lancet.find_executable import run_and_disown, find_executable
from lancet.notifications import NotifySend
from lancet.ocr.manga_ocr_launcher import MangaOCRLauncher, run_ocr
from lancet.ocr.op import QThreadPoolOp


def make_output_file_path() -> pathlib.Path:
    return pathlib.Path.home() / "Pictures" / "Screenshots" / f"{datetime.datetime.now().isoformat()}.png"


class LancetSystemTray(QSystemTrayIcon):
    """
    System tray application containing all global actions
    """

    _ocr: MangaOCRLauncher
    _scr: ZalaScreenshot
    _app: QApplication
    _sel: ZalaSelect | None = None
    _cfg: Config

    def __init__(self, app: QApplication, parent=None) -> None:
        super().__init__(parent)
        self._app = app
        self._scr = ZalaScreenshot(app)

        # State trackers and configurations
        self.threadpool = QThreadPool.globalInstance()
        self._cfg = Config.read_from_file()
        self._ocr = MangaOCRLauncher(
            parent=self,
            threadpool=self.threadpool,
            pretrained_model_name_or_path=self._cfg.huggingface_model_name,
            force_cpu=self._cfg.force_cpu,
        )
        self._notify = NotifySend(self, duration_sec=self._cfg.notification_duration_sec)
        # self.loadHotkeys()
        self.setIcon(QIcon(str(APP_LOGO_PATH)))
        # Menu
        menu = QMenu(parent)
        self.setContextMenu(menu)

        # Menu Actions
        menu.addAction(QIcon(str(SCREENSHOT_ICON_PATH)), "Make screenshot", self.make_screenshot)
        menu.addAction(QIcon(str(OCR_ICON_PATH)), "OCR screenshot", self.make_ocr_screenshot)
        menu.addAction(QIcon(str(EXIT_ICON_PATH)), "Exit", self.quit)

        # Init model in background
        self._ocr.init_manga_ocr()
        signal.signal(signal.SIGINT, self.quit)

    def quit(self) -> None:
        logger.info("Quit Lancet.")
        self._app.quit()

    def make_screenshot(self) -> None:
        self._sel = ZalaSelect(self._scr.capture_screen())
        self._sel.selection_finished.connect(self.process_select_result)
        self._sel.showFullScreen()

    def make_ocr_screenshot(self) -> None:
        self._sel = ZalaSelect(self._scr.capture_screen())
        self._sel.selection_finished.connect(self.process_ocr_result)
        self._sel.showFullScreen()

    def process_select_result(self, user_selection: UserSelectionResult) -> None:
        if not user_selection.pixmap:
            self._notify.notify("Selection aborted")
            return
        output_path = make_output_file_path()
        output_path.mkdir(parents=True, exist_ok=True)
        if user_selection.pixmap.save(str(output_path)):
            self._notify.notify(f"Selection saved to {output_path}")
        else:
            self._notify.notify(f"Failed to save selection to {output_path}")

    def process_ocr_result(self, user_selection: UserSelectionResult) -> None:
        if not user_selection.pixmap:
            self._notify.notify(user_selection.error.capitalize())
            return
        if not self._ocr.is_ready():
            self._notify.notify(f"OCR model is not ready.")
            return

        def on_ocr_finished(text: str) -> None:
            if text:
                self.copy_ocr_result(text)
                self._notify.notify(f"OCR result copied: {text}")
            else:
                self._notify.notify("OCR returned no text")

        def on_failed(e: Exception) -> None:
            logger.error(f"failed to recognize image: {e}")
            self._notify.notify(f"failed to recognize image: {e}")

        (
            QThreadPoolOp(parent=self, op=lambda: run_ocr(user_selection.pixmap, self._ocr), threadpool=self.threadpool)
            .success(on_ocr_finished)
            .failure(on_failed)
            .run_in_background()
        )

    def copy_ocr_result(self, text: str) -> None:
        match self._cfg.copy_to:
            case OcrDestination.goldendict:
                run_and_disown([find_executable("goldendict") or "goldendict", text])
            case OcrDestination.clipboard:
                self._app.clipboard().setText(text)
