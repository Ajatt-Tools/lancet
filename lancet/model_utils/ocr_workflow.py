# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import concurrent.futures
from collections.abc import Callable
from io import BytesIO

from loguru import logger
from PIL import Image
from PyQt6.QtCore import QBuffer
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QApplication
from zala.main_window import UserSelectionResult

from lancet.config import Config, OcrDestination
from lancet.exceptions import PixmapConversionError
from lancet.find_executable import find_executable, run_and_disown
from lancet.model_utils.base import ModelName
from lancet.model_utils.model_loader import BackgroundModelLoader
from lancet.model_utils.ocr_service import OcrService
from lancet.notifications import NotifySend
from lancet.ocr.thread_op import LancetThreadOp
from lancet.ocr_history import OcrHistory


def ensure_cursor_restored() -> None:
    """Safety net: restore the cursor if Zala left it in an override state."""
    if QApplication.overrideCursor() is not None:
        QApplication.restoreOverrideCursor()


def pixmap_to_pillow_image(pixmap: QPixmap) -> Image.Image:
    """Convert a Qt QPixmap to a PIL Image. Raise if the pixmap is empty."""
    if pixmap.isNull():
        raise PixmapConversionError("pixmap is null")

    buffer = QBuffer()
    buffer.open(QBuffer.OpenModeFlag.ReadWrite)
    pixmap.save(buffer, "PNG")
    # https://doc.qt.io/qt-6/qbuffer.html#data
    # https://doc.qt.io/qt-6/qbytearray.html#data
    bytes_io = BytesIO(buffer.data().data())

    if bytes_io.getbuffer().nbytes == 0:
        raise PixmapConversionError("empty pixmap")

    image = Image.open(bytes_io)
    if not (image.width > 0 and image.height > 0):
        raise PixmapConversionError("image is empty")
    return image


def prepare_pillow_image(user_selection: UserSelectionResult) -> Image.Image:
    """Validate user selection and convert to PIL Image, or raise."""
    if not user_selection.pixmap:
        raise PixmapConversionError(user_selection.error.capitalize())
    return pixmap_to_pillow_image(user_selection.pixmap)


class OcrWorkflow:
    """Handles the end-to-end OCR workflow from user screen selection to clipboard."""

    def __init__(
        self,
        *,
        app: QApplication,
        cfg: Config,
        loader: BackgroundModelLoader,
        ocr_service: OcrService,
        notify: NotifySend,
        history: OcrHistory,
        executor: concurrent.futures.ThreadPoolExecutor,
    ) -> None:
        """Initialize the workflow with all required dependencies."""
        self._app = app
        self._cfg = cfg
        self._loader = loader
        self._ocr_service = ocr_service
        self._notify = notify
        self._history = history
        self._executor = executor

    def run_ocr(self, user_selection: UserSelectionResult) -> None:
        """Run single-region OCR from user selection."""
        ensure_cursor_restored()
        if not self._loader.is_model_ready(ModelName.manga_ocr):
            self._notify.notify(self._loader.status().what())
            return

        try:
            image = prepare_pillow_image(user_selection)
        except PixmapConversionError as ex:
            self._notify.notify(str(ex))
            return

        self._submit_ocr_task(op=lambda: self._ocr_service.run_ocr(image))

    def run_speech_bubble_ocr(self, user_selection: UserSelectionResult) -> None:
        """Run speech bubble detection + OCR from user selection."""
        ensure_cursor_restored()
        if not self._loader.is_model_ready(ModelName.manga_ocr, ModelName.text_detector):
            self._notify.notify(self._loader.status().what())
            return

        try:
            image = prepare_pillow_image(user_selection)
        except PixmapConversionError as ex:
            self._notify.notify(str(ex))
            return

        self._submit_ocr_task(op=lambda: self._ocr_service.run_ocr_with_text_detection(image))

    def copy_ocr_result(self, text: str) -> None:
        """Send the OCR result to the configured destination (clipboard or GoldenDict)."""
        match self._cfg.copy_to:
            case OcrDestination.goldendict:
                try:
                    run_and_disown([find_executable("goldendict") or "goldendict", text])
                except FileNotFoundError:
                    self._notify.notify(
                        "Executable not found: 'goldendict'. Ensure it is installed and added to $PATH."
                    )
                    return
            case OcrDestination.clipboard:
                clipboard = self._app.clipboard()
                if clipboard is None:
                    logger.error("Clipboard is not available")
                    self._notify.notify("Clipboard is not available")
                    return
                clipboard.setText(text)
        self._notify.notify(f"OCR result copied: {text}")

    def _submit_ocr_task(self, *, op: Callable[[], str]) -> None:
        """Submit an OCR task to the background thread with shared success/failure callbacks."""
        (
            LancetThreadOp[str](op=op, executor=self._executor)
            .success(self._on_ocr_finished)
            .failure(self._on_ocr_failed)
            .run_in_background()
        )

    def _on_ocr_finished(self, text: str) -> None:
        """Handle successful OCR result."""
        if text:
            self._history.add_to_history(text)
            self.copy_ocr_result(text)
        else:
            self._notify.notify("OCR returned no text")

    def _on_ocr_failed(self, e: Exception) -> None:
        """Handle failed OCR."""
        logger.error(f"Failed to recognize image: {e}")
        self._notify.notify(f"Failed to recognize image: {e}")
