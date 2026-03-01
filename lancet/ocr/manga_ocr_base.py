# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import abc
import pathlib

from PIL import Image


class MangaOcrBase(abc.ABC):
    """Abstract base class defining the interface for manga OCR implementations."""

    @abc.abstractmethod
    def recognize(self, img_or_path: str | pathlib.Path | Image.Image) -> str:
        """Recognize text in the given image or image file path and return it as a string."""
        raise NotImplementedError


class MangaOCRException(Exception):
    """Base exception for all manga OCR related errors."""

    pass


class MangaOCRFileNotFoundError(MangaOCRException, FileNotFoundError):
    """Raised when a required file (e.g. example image) is not found."""

    pass


class ConfigReadError(MangaOCRException, RuntimeError):
    """Raised when the configuration file cannot be read or parsed."""

    pass
