# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
import os

from loguru import logger
from PIL import Image

from lancet.config import Config
from lancet.consts import CACHE_DIR_PATH, OCR_JOIN_STR
from lancet.model_utils.model_loader import BackgroundModelLoader
from lancet.model_utils.common import save_bubble_images


class OcrService:
    """Runs OCR on images, optionally using text detection to isolate speech bubbles first."""

    def __init__(self, *, loader: BackgroundModelLoader, cfg: Config) -> None:
        """Initialize with a reference to the background model loader."""
        self._loader = loader
        self._cfg = cfg

    def run_ocr(self, image: Image.Image) -> str:
        """
        Run OCR directly on the image.
        Convert PIL Image object to text using the OCR model
        """
        return self._loader.ocr.recognize(image).strip()

    def run_ocr_with_text_detection(self, image: Image.Image) -> str:
        """
        Detect speech bubbles, run OCR on each box image, and concatenate the results.
        """
        bubbles = self._loader.text_detector.get_speech_bubbles(
            image,
            include_lines=False,
            keep_undetected_mask=self._cfg.recover_missed_text,
        )
        if "LANCET_DEBUG" in os.environ:
            save_bubble_images(bubbles.blocks, output_dir=CACHE_DIR_PATH / "debug_speech_bubbles")
            logger.debug(f"saved bubbles to {CACHE_DIR_PATH / "debug_speech_bubbles"}")

        return OCR_JOIN_STR.join(self._loader.ocr.recognize(block.box_image).strip() for block in bubbles.blocks)
