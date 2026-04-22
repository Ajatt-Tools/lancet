# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import abc
import pathlib

from PIL import Image

from lancet.base import LancetModel
from lancet.exceptions import LancetException

EXAMPLE_IMAGE_PATH = pathlib.Path(__file__).parent / "assets/example.jpg"


class MangaOcrBase(LancetModel):
    """Abstract base class defining the interface for manga OCR implementations."""

    @property
    @abc.abstractmethod
    def pretrained_model_name_or_path(self) -> pathlib.Path | str:
        """
        Return the HuggingFace repo ID or local path used to load the pretrained model.
        Example: "tatsumoto/manga-ocr-base"
        """
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def force_cpu(self) -> bool:
        """Return whether the model was loaded with CPU forced."""
        raise NotImplementedError

    @abc.abstractmethod
    def recognize(self, img_or_path: str | pathlib.Path | Image.Image) -> str:
        """Recognize text in the given image or image file path and return it as a string."""
        raise NotImplementedError


class MangaOCRException(LancetException):
    """Base exception for all manga OCR related errors."""

    pass


class MangaOCRFileNotFoundError(MangaOCRException, FileNotFoundError):
    """Raised when a required file (e.g. example image) is not found."""

    pass
