# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
import pathlib
import typing
from io import BytesIO

from PIL import Image
from PyQt6.QtCore import QBuffer, QThreadPool, QObject
from PyQt6.QtGui import QPixmap
from loguru import logger

from lancet.notifications import NotifySend
from lancet.ocr.manga_ocr_base import MangaOcrBase, MangaOCRException
from lancet.ocr.op import QThreadPoolOp


class MangaOCRReadyResult(typing.NamedTuple):
    is_ready: bool
    error: Exception | None

    def what(self) -> str:
        if self.is_ready:
            return "OCR is ready."
        if self.error:
            return f"OCR model is not ready. {self.error}."
        return "OCR model is not ready."


class MangaOCRLauncher:
    """
    Manages the lifecycle of the manga OCR model, handling background initialization and readiness checks.
    Used to wrap the MangaOcr class since it is extremely slow to import.
    """

    _class_instance: MangaOcrBase | None = None
    _error: Exception | None = None

    def __init__(
        self,
        parent: QObject,
        notify: NotifySend,
        threadpool: QThreadPool,
        pretrained_model_name_or_path: str | pathlib.Path = "tatsumoto/manga-ocr-base",
        force_cpu: bool = False,
    ) -> None:
        """Initialize the launcher with configuration for model loading."""
        super().__init__()
        self._parent = parent
        self._notify = notify
        self._threadpool = threadpool
        self._pretrained_model_name_or_path = pretrained_model_name_or_path
        self._force_cpu = force_cpu
        self._class_instance = None
        self._error = None

    def load_new_config(self, model_name: str, force_cpu: bool) -> None:
        """Update model configuration and reload the model in the background if it changed."""
        reload_needed = model_name != self._pretrained_model_name_or_path or force_cpu != self._force_cpu
        self._pretrained_model_name_or_path = model_name
        self._force_cpu = force_cpu
        if reload_needed:
            logger.info(f"OCR config changed, reloading model: {model_name}, force_cpu={force_cpu}")
            self._class_instance = None
            self.init_manga_ocr()

    def is_ready(self) -> MangaOCRReadyResult:
        """Return whether the OCR model has been loaded and is ready to use."""
        return MangaOCRReadyResult(bool(self._class_instance), self._error)

    def init_manga_ocr(self) -> None:
        """Start loading the OCR model in a background thread."""

        def op() -> MangaOcrBase:
            from lancet.ocr.manga_ocr import MangaOcr

            mocr = MangaOcr(
                pretrained_model_name_or_path=self._pretrained_model_name_or_path,
                force_cpu=self._force_cpu,
            )
            return mocr

        def on_ready(model: MangaOcrBase) -> None:
            self._class_instance = model
            self._notify.notify(f"OCR ready")

        def on_failed(e: Exception) -> None:
            logger.error(f"failed to initialize manga ocr: {e}")
            self._notify.notify(f"failed to initialize manga ocr: {e}")
            self._error = e

        (
            QThreadPoolOp(parent=self._parent, op=op, threadpool=self._threadpool)
            .success(on_ready)
            .failure(on_failed)
            .run_in_background()
        )

    @property
    def instance(self) -> MangaOcrBase:
        """Return the loaded OCR model instance, raising an exception if not yet initialized."""
        if not self._class_instance:
            raise MangaOCRException("ocr model is not initialized")
        return self._class_instance


def pixmap_to_pillow_image(pixmap: QPixmap) -> Image.Image | None:
    """Convert a Qt QPixmap to a PIL Image, returning None if the pixmap is empty."""
    buffer = QBuffer()
    buffer.open(QBuffer.OpenModeFlag.ReadWrite)
    pixmap.save(buffer, "PNG")
    bytes_io = BytesIO(buffer.data())

    if bytes_io.getbuffer().nbytes == 0:
        return None

    return Image.open(bytes_io)


def run_ocr(pixmap: QPixmap, model: MangaOCRLauncher) -> str:
    """
    Convert QPixmap object to text using the OCR model
    """
    image = pixmap_to_pillow_image(pixmap)
    if not image:
        raise MangaOCRException("empty pixmap")
    return model.instance.recognize(image).strip()
