# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
import pathlib
from io import BytesIO

from PIL import Image
from PyQt6.QtCore import QBuffer, QThreadPool, QObject
from PyQt6.QtGui import QPixmap
from loguru import logger

from lancet.notifications import NotifySend
from lancet.ocr.manga_ocr_base import MangaOcrBase, MangaOCRException
from lancet.ocr.op import QThreadPoolOp


class MangaOCRLauncher:
    _class_instance: MangaOcrBase | None = None

    def __init__(
        self,
        parent: QObject,
        notify: NotifySend,
        threadpool: QThreadPool,
        pretrained_model_name_or_path: str | pathlib.Path = "tatsumoto/manga-ocr-base",
        force_cpu: bool = False,
    ) -> None:
        super().__init__()
        self._parent = parent
        self._notify = notify
        self._threadpool = threadpool
        self._pretrained_model_name_or_path = pretrained_model_name_or_path
        self._force_cpu = force_cpu
        self._class_instance = None

    def is_ready(self) -> bool:
        return bool(self._class_instance)

    def init_manga_ocr(self) -> None:
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

        (
            QThreadPoolOp(parent=self._parent, op=op, threadpool=self._threadpool)
            .success(on_ready)
            .failure(on_failed)
            .run_in_background()
        )

    @property
    def instance(self) -> MangaOcrBase:
        if not self._class_instance:
            raise MangaOCRException("ocr model is not initialized")
        return self._class_instance


def pixmap_to_pillow_image(pixmap: QPixmap) -> Image.Image | None:
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
