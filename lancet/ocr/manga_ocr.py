# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import pathlib
import re

import jaconv
import torch
from PIL import Image
from loguru import logger
from transformers import ViTImageProcessor, AutoTokenizer, VisionEncoderDecoderModel, GenerationMixin

from lancet.ocr.manga_ocr_base import MangaOcrBase, MangaOCRFileNotFoundError, MangaOCRException, EXAMPLE_IMAGE_PATH


class MangaOcrModel(VisionEncoderDecoderModel, GenerationMixin):
    """Combined vision encoder-decoder model with generation capabilities for manga OCR."""

    pass


def class_name(obj: object) -> str:
    return obj.__class__.__name__


class MangaOcr(MangaOcrBase):
    """
    Manga OCR implementation that uses a HuggingFace vision encoder-decoder model
    to recognize Japanese text in manga images.
    """

    # possible options for pretrained_model_name_or_path:
    # "tatsumoto/manga-ocr-base"
    # "jzhang533/manga-ocr-base-2025"
    # "kha-white/manga-ocr-base" (not a safetensors model, not recommended)

    def __init__(
        self,
        pretrained_model_name_or_path: pathlib.Path | str = "tatsumoto/manga-ocr-base",
        force_cpu: bool = False,
    ) -> None:
        """Load the OCR model, tokenizer, and processor, then verify with an example image."""
        logger.info(f"Loading OCR model from {pretrained_model_name_or_path}")
        try:
            self._load_model(pretrained_model_name_or_path)
        except Exception as ex:
            raise MangaOCRException(f"{class_name(ex)}: {ex}") from ex

        if not force_cpu and torch.cuda.is_available():
            logger.info("Using CUDA")
            self.model.cuda()
        elif not force_cpu and torch.backends.mps.is_available():
            logger.info("Using MPS")
            self.model.to("mps")
        else:
            logger.info("Using CPU")

        if not EXAMPLE_IMAGE_PATH.is_file():
            raise MangaOCRFileNotFoundError(f"Missing example image {EXAMPLE_IMAGE_PATH}")
        logger.info(self.recognize(EXAMPLE_IMAGE_PATH))
        logger.info("OCR ready")

    def _load_model(self, pretrained_model_name_or_path: pathlib.Path | str) -> None:
        try:
            self._load_from_pretrained(pretrained_model_name_or_path, local_files_only=True)
        except OSError as ex:
            logger.error(f"{class_name(ex)}: {ex}")
            logger.info(f"trying with local_files_only=False")
            self._load_from_pretrained(pretrained_model_name_or_path, local_files_only=False)

    def _load_from_pretrained(
        self, pretrained_model_name_or_path: pathlib.Path | str, *, local_files_only: bool
    ) -> None:
        # local_files_only = Whether to only look at local files (i.e., do not try to download the model).
        # Cache location example: "~/.cache/huggingface/hub/models--tatsumoto--manga-ocr-base/snapshots/"
        self.processor = ViTImageProcessor.from_pretrained(
            pretrained_model_name_or_path,
            local_files_only=local_files_only,
        )
        self.tokenizer = AutoTokenizer.from_pretrained(
            pretrained_model_name_or_path,
            local_files_only=local_files_only,
        )
        self.model = MangaOcrModel.from_pretrained(
            pretrained_model_name_or_path,
            local_files_only=local_files_only,
        )

    def recognize(self, img_or_path: str | pathlib.Path | Image.Image) -> str:
        """Recognize Japanese text in the given image or image file path."""
        if isinstance(img_or_path, str) or isinstance(img_or_path, pathlib.Path):
            img = Image.open(img_or_path)
        elif isinstance(img_or_path, Image.Image):
            img = img_or_path
        else:
            raise MangaOCRException(f"img_or_path must be a path or PIL.Image, instead got: {img_or_path}")

        img = img.convert("L").convert("RGB")

        x = self._preprocess(img)
        x = self.model.generate(x[None].to(self.model.device), max_length=300)[0].cpu()
        x = self.tokenizer.decode(x, skip_special_tokens=True)
        x = post_process(x)
        return x

    def _preprocess(self, img: Image.Image) -> torch.Tensor:
        """Convert a PIL image to a tensor suitable for the model's input."""
        pixel_values = self.processor(img, return_tensors="pt").pixel_values
        return pixel_values.squeeze()


def post_process(text: str) -> str:
    """Clean up OCR output by normalizing whitespace, punctuation, and converting to full-width characters."""
    text = "".join(text.split())
    text = text.replace("...", "…")
    text = re.sub("[・.]{2,}", lambda x: (x.end() - x.start()) * ".", text)
    text = jaconv.h2z(text, ascii=True, digit=True)

    return text


def main() -> None:
    """Create a MangaOcr instance for testing purposes."""
    mocr = MangaOcr()


if __name__ == "__main__":
    main()
