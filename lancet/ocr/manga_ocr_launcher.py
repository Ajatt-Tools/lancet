# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
import pathlib
from io import BytesIO
from threading import Thread
from typing import Self

from PIL import Image
from PyQt6.QtCore import QBuffer
from PyQt6.QtGui import QPixmap


class Singleton:
    _instance: None | Self = None

    def __new__(cls, *args, **kwargs) -> Self:
        if not isinstance(cls._instance, cls):
            cls._instance = object.__new__(cls, *args, **kwargs)
        return cls._instance


class MangaOCRException(Exception):
    pass


class MangaOCRLauncher(Singleton):
    _thread:Thread | None

    def __init__(
            self,
            pretrained_model_name_or_path: str | pathlib.Path = "tatsumoto/manga-ocr-base",
            force_cpu: bool = False,
    ) -> None:
        super().__init__()
        self._pretrained_model_name_or_path = pretrained_model_name_or_path
        self._force_cpu = force_cpu
        self._class_instance = None
        self._thread = None

    def init_model(self) -> Self:
        from lancet.ocr.manga_ocr import MangaOcr
        self._class_instance = MangaOcr(
            pretrained_model_name_or_path=self._pretrained_model_name_or_path,
            force_cpu=self._force_cpu,
        )
        return self

    def recognize(self, img_or_path: str | pathlib.Path | Image.Image) -> str:
        if self._class_instance is None:
            raise MangaOCRException("ocr model should be initialized")
        return self._class_instance.recognize(img_or_path)


def pixmap_to_pillow_image(pixmap: QPixmap) -> Image.Image | None:
    buffer = QBuffer()
    buffer.open(QBuffer.OpenModeFlag.ReadWrite)
    pixmap.save(buffer, "PNG")
    bytes_io = BytesIO(buffer.data())

    if bytes_io.getbuffer().nbytes == 0:
        return None

    return Image.open(bytes_io)


def run_ocr(pixmap: QPixmap, model: MangaOCRLauncher | None = None) -> str:
    """
    Convert QPixmap object to text using the OCR model
    """
    if not model:
        return ""
    image = pixmap_to_pillow_image(pixmap)
    if not image:
        return ""
    return model.recognize(image).strip()
