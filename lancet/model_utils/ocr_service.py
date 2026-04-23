# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from PIL import Image

from lancet.consts import OCR_JOIN_STR
from lancet.model_utils.model_loader import BackgroundModelLoader


class OcrService:
    """Runs OCR on images, optionally using text detection to isolate speech bubbles first."""

    def __init__(self, *, loader: BackgroundModelLoader) -> None:
        """Initialize with a reference to the background model loader."""
        self._loader = loader

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
        return OCR_JOIN_STR.join(
            self._loader.ocr.recognize(block.box_image).strip()
            for block in self._loader.text_detector.get_speech_bubbles(image, include_lines=False).blocks
        )
