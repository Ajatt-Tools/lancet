# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from lancet.exceptions import LancetException


class MangaOCRException(LancetException):
    """Base exception for all manga OCR related errors."""

    pass


class MangaOCRLoadError(MangaOCRException):
    """Raised when the OCR model, tokenizer, or processor fails to load."""

    pass


class MangaOCRTokenizerLoadError(MangaOCRLoadError):
    """Raised when the OCR tokenizer cannot be loaded."""

    pass


class MangaOCRTokenizerFileNotFoundError(MangaOCRTokenizerLoadError, FileNotFoundError):
    """Raised when a model snapshot lacks a required OCR tokenizer file."""

    pass


class MangaOCRUnavailableError(MangaOCRException):
    """Manga OCR model is still loading."""

    pass


class MangaOCRFileNotFoundError(MangaOCRException, FileNotFoundError):
    """Raised when a required file (e.g. example image) is not found."""

    pass
