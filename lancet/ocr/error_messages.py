# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
import pathlib

from lancet.model_utils.common import class_name
from lancet.ocr.manga_ocr_base import MangaOCRTokenizerLoadError

BACKEND_TOKENIZER_ERROR: str = "Couldn't instantiate the backend tokenizer"


def adjust_auto_tokenizer_error_message(ex: Exception, model_name: pathlib.Path | str) -> MangaOCRTokenizerLoadError:
    """Return a user-facing error for AutoTokenizer failures."""
    if BACKEND_TOKENIZER_ERROR in str(ex):
        return MangaOCRTokenizerLoadError(
            f"Failed to load OCR tokenizer for '{model_name}'. "
            f"Transformers could not load the fast tokenizer backend. "
            f"This usually means the cached model snapshot is outdated or missing tokenizer.json. "
            f"Lancet will try the slow BertJapaneseTokenizer fallback. "
            f"Try clearing the cached snapshot for this model under "
            f"~/.cache/huggingface/hub/ and restart Lancet."
        )
    return MangaOCRTokenizerLoadError(
        f"Failed to load OCR tokenizer for '{model_name}'. " f"AutoTokenizer failed with {class_name(ex)}: {ex}."
    )


def adjust_slow_tokenizer_error_message(ex: Exception, model_name: pathlib.Path | str) -> MangaOCRTokenizerLoadError:
    """Return a user-facing error for BertJapaneseTokenizer fallback failures."""
    error_msg = str(ex).lower()
    if "fugashi" in error_msg or "unidic" in error_msg or "mecab" in error_msg:
        return MangaOCRTokenizerLoadError(
            f"Failed to load OCR tokenizer for '{model_name}'. "
            f"BertJapaneseTokenizer fallback failed with {class_name(ex)}: {ex}. "
            f"This may indicate missing Japanese tokenizer files for fugashi/unidic_lite."
        )
    return MangaOCRTokenizerLoadError(
        f"Failed to load OCR tokenizer for '{model_name}'. "
        f"BertJapaneseTokenizer fallback failed with {class_name(ex)}: {ex}."
    )


def adjust_error_message(ex: OSError, model_name: pathlib.Path | str) -> OSError:
    """Return a copy of ex with a helpful message for known HuggingFace transformers errors."""
    error_msg = str(ex).lower()
    # The "Unable to load vocabulary" error often means PyInstaller didn't bundle
    # fugashi/unidic_lite data files, not that the vocabulary file is corrupted.
    if "vocabulary" in error_msg:
        return OSError(
            f"{ex}. "
            f"This may indicate missing files for fugashi/unidic_lite "
            f"(commonly happens in PyInstaller builds)."
        )
    elif "preprocessor_config" in error_msg or "image processor" in error_msg:
        return OSError(
            f"'{model_name}' is not a compatible HuggingFace transformers model. "
            f"It may be in TFLite, ONNX, or another unsupported format. "
            f"Lancet supports safetensors models like 'tatsumoto/manga-ocr-base' or 'jzhang533/manga-ocr-base-2025'."
        )
    elif "not a valid model identifier" in error_msg or "couldn't find" in error_msg:
        return OSError(
            f"Model '{model_name}' was not found on HuggingFace Hub. Check the spelling or verify the model exists."
        )
    elif "connection" in error_msg or "offline" in error_msg or "couldn't connect" in error_msg:
        return OSError(f"Cannot reach HuggingFace Hub to load '{model_name}'. Check your internet connection.")
    return ex
