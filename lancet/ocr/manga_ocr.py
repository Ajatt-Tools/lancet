# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import pathlib
import re

import jaconv
import numpy as np
import torch
from PIL import Image
from loguru import logger
from transformers import ViTImageProcessor, AutoTokenizer, VisionEncoderDecoderModel, GenerationMixin


class MangaOcrModel(VisionEncoderDecoderModel, GenerationMixin):
    pass


class MangaOcr:
    # possible options for pretrained_model_name_or_path:
    # "tatsumoto/manga-ocr-base"
    # "jzhang533/manga-ocr-base-2025"
    # "kha-white/manga-ocr-base" (not a safetensors model, not recommended)

    def __init__(
            self,
            pretrained_model_name_or_path: pathlib.Path | str = "tatsumoto/manga-ocr-base",
            force_cpu: bool = False,
    ) -> None:
        logger.info(f"Loading OCR model from {pretrained_model_name_or_path}")
        self.processor = ViTImageProcessor.from_pretrained(pretrained_model_name_or_path)
        self.tokenizer = AutoTokenizer.from_pretrained(pretrained_model_name_or_path)
        self.model = MangaOcrModel.from_pretrained(pretrained_model_name_or_path)

        if not force_cpu and torch.cuda.is_available():
            logger.info("Using CUDA")
            self.model.cuda()
        elif not force_cpu and torch.backends.mps.is_available():
            logger.info("Using MPS")
            self.model.to("mps")
        else:
            logger.info("Using CPU")

        example_path = pathlib.Path(__file__).parent / "assets/example.jpg"
        if not example_path.is_file():
            raise FileNotFoundError(f"Missing example image {example_path}")
        logger.info(self.recognize(example_path))
        logger.info("OCR ready")

    def recognize(self, img_or_path: str | pathlib.Path | Image.Image) -> str:
        if isinstance(img_or_path, str) or isinstance(img_or_path, pathlib.Path):
            img = Image.open(img_or_path)
        elif isinstance(img_or_path, Image.Image):
            img = img_or_path
        else:
            raise ValueError(f"img_or_path must be a path or PIL.Image, instead got: {img_or_path}")

        img = img.convert("L").convert("RGB")

        x = self._preprocess(img)
        x = self.model.generate(x[None].to(self.model.device), max_length=300)[0].cpu()
        x = self.tokenizer.decode(x, skip_special_tokens=True)
        x = post_process(x)
        return x

    def _preprocess(self, img: Image.Image) -> np.ndarray:
        pixel_values = self.processor(img, return_tensors="pt").pixel_values
        return pixel_values.squeeze()


def post_process(text: str) -> str:
    text = "".join(text.split())
    text = text.replace("...", "…")
    text = re.sub("[・.]{2,}", lambda x: (x.end() - x.start()) * ".", text)
    text = jaconv.h2z(text, ascii=True, digit=True)

    return text


def main() -> None:
    mocr = MangaOcr()


if __name__ == "__main__":
    main()
