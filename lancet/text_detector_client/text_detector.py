# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import pathlib
import typing

import cv2
import numpy as np
from loguru import logger
from PIL import Image
from torch.signal.windows import gaussian

from comic_text_detector.inference import TextDetector
from comic_text_detector.utils.textblock import TextBlock
from lancet.__about__ import version
from lancet.consts import CACHE_DIR_PATH
from lancet.model_utils.common import class_name, save_bubble_images
from lancet.model_utils.device import get_device
from lancet.ocr.manga_ocr_base import EXAMPLE_IMAGE_PATH
from lancet.text_detector_client.model_cache import ComicTextDetectorCache
from lancet.text_detector_client.text_detector_base import (
    ComicTextDetectorBase,
    ComicTextDetectorException,
    Quad,
    Rect,
    SpeechBubbleBlock,
    SpeechBubbleResult,
)


def read_image_from_path(imgpath: pathlib.Path, read_type: int = cv2.IMREAD_COLOR) -> np.ndarray:
    """cv2.imread, but works with Unicode paths. Raises on failure."""
    result = cv2.imdecode(np.fromfile(imgpath, dtype=np.uint8), read_type)
    if result is None:
        raise ComicTextDetectorException(
            f"Failed to read image: {imgpath}. Possible cause: Animation file, Corrupted file or Unsupported type"
        )
    return result


def crop_box_region(img: np.ndarray, rect: Rect) -> Image.Image:
    """Crop the bounding box region from a BGR image and return it as a PIL Image."""
    cropped = img[rect.y1 : rect.y2, rect.x1 : rect.x2]
    if cropped.size <= 0:
        raise ComicTextDetectorException(f"crop region is empty: rect={rect}, image shape={img.shape}")
    return Image.fromarray(cv2.cvtColor(cropped, cv2.COLOR_BGR2RGB))


def pil_image_to_bgr_array(image: Image.Image) -> np.ndarray:
    """Convert a PIL Image to a BGR numpy array as expected by OpenCV."""
    rgb = np.array(image)
    if rgb.size <= 0:
        raise ComicTextDetectorException(
            f"cannot convert an empty PIL image to BGR (mode={image.mode}, size={image.size})"
        )
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


class DetectResult(typing.NamedTuple):
    mask: np.ndarray
    mask_refined: np.ndarray
    blk_list: list[TextBlock]


class ComicTextDetector(ComicTextDetectorBase):
    """
    Wraps TextDetector class.
    """

    def __init__(
        self,
        force_cpu: bool = False,
        detector_input_size: int = 1024,
        text_height: int = 64,
        max_ratio_vert: int = 16,
        max_ratio_hor: int = 8,
        anchor_window: int = 2,
    ) -> None:
        """Load the TextDetector model, tokenizer, and processor, then verify with an example image."""
        self._force_cpu = force_cpu
        self._detector_input_size = detector_input_size
        self._text_height = text_height
        self._max_ratio_vert = max_ratio_vert
        self._max_ratio_hor = max_ratio_hor
        self._anchor_window = anchor_window
        cache = ComicTextDetectorCache()
        logger.info(f"Loading TextDetector model from {cache.comic_text_detector_path()}")

        try:
            self._detector = TextDetector(
                model_path=cache.comic_text_detector_path(),
                input_size=self._detector_input_size,
                device=get_device(force_cpu=self._force_cpu).name.lower(),
                act="leaky",
            )
        except Exception as ex:
            raise ComicTextDetectorException(f"{class_name(ex)}: {ex}") from ex
        logger.info(f"TextDetector uses {self._detector.device.upper()}")
        logger.info(f"TextDetector ready")

    @property
    def force_cpu(self) -> bool:
        """Return whether the model was loaded with CPU forced."""
        return self._force_cpu

    @property
    def detector_input_size(self) -> int:
        """Return the input resolution used by the text detector."""
        return self._detector_input_size

    def _detect_text(self, img: np.ndarray, *, keep_undetected_mask: bool = True) -> DetectResult:
        """Detect text in the given image."""
        return DetectResult(*self._detector.__call__(img, refine_mode=1, keep_undetected_mask=keep_undetected_mask))

    def get_speech_bubbles(
        self,
        img_or_path: pathlib.Path | Image.Image,
        *,
        include_lines: bool = False,
        keep_undetected_mask: bool = True,
    ) -> SpeechBubbleResult:
        """
        Detect speech bubbles in the given image or image file path.
        Do not include lines by default because they are not used by Lancet.
        """
        if isinstance(img_or_path, Image.Image):
            img = pil_image_to_bgr_array(img_or_path)
        else:
            img = read_image_from_path(img_or_path)

        img_height, img_width, *_ = img.shape
        result = SpeechBubbleResult(version=version, img_width=img_width, img_height=img_height)

        detected = self._detect_text(img, keep_undetected_mask=keep_undetected_mask)
        for blk in detected.blk_list:
            rect = Rect.new(blk.xyxy).clamp(img_width=img_width, img_height=img_height)
            if not rect.has_area():
                logger.warning(f"Skipping degenerate text block with zero area rect: {rect}")
                continue
            result_blk = SpeechBubbleBlock(
                box=rect,
                box_image=crop_box_region(img, rect),
                vertical=bool(blk.vertical),
                font_size=float(blk.font_size),
            )
            if not include_lines:
                result.blocks.append(result_blk)
                continue

            for line_idx, line in enumerate(blk.lines_array()):
                if blk.vertical:
                    max_ratio = self._max_ratio_vert
                else:
                    max_ratio = self._max_ratio_hor

                line_crops, cut_points = self._split_into_chunks(
                    img,
                    detected.mask_refined,
                    blk,
                    line_idx,
                    textheight=self._text_height,
                    max_ratio=max_ratio,
                    anchor_window=self._anchor_window,
                )

                images = []
                for line_crop in line_crops:
                    if blk.vertical:
                        line_crop = cv2.rotate(line_crop, cv2.ROTATE_90_CLOCKWISE)
                    images.append(Image.fromarray(line_crop))

                result_blk.lines_coords.append(Quad.from_nested(line.tolist()))
                result_blk.lines.append(images)

            result.blocks.append(result_blk)

        return result

    @staticmethod
    def _split_into_chunks(
        img: np.ndarray,
        mask_refined: np.ndarray,
        blk: TextBlock,
        line_idx: int,
        textheight: int,
        max_ratio: int = 16,
        anchor_window: int = 2,
    ) -> tuple[list[np.ndarray], list[int]]:
        line_crop = blk.get_transformed_region(img, line_idx, textheight)

        h, w, *_ = line_crop.shape
        ratio = w / h

        if ratio <= max_ratio:
            return [line_crop], []

        else:
            k = gaussian(textheight * 2, std=textheight / 8)

            line_mask = blk.get_transformed_region(mask_refined, line_idx, textheight)
            num_chunks = int(np.ceil(ratio / max_ratio))

            anchors = np.linspace(0, w, num_chunks + 1)[1:-1]

            line_density = line_mask.sum(axis=0)
            line_density = np.convolve(line_density, k, "same")
            line_density /= line_density.max()

            anchor_window *= textheight

            cut_points = []
            for anchor in anchors:
                anchor = int(anchor)

                n0 = np.clip(anchor - anchor_window // 2, 0, w)
                n1 = np.clip(anchor + anchor_window // 2, 0, w)

                p = line_density[n0:n1].argmin()
                p += n0

                cut_points.append(p)

            return np.split(line_crop, cut_points, axis=1), cut_points


def main() -> None:
    """Create a ComicTextDetector instance for testing purposes."""
    detector = ComicTextDetector()
    result = detector.get_speech_bubbles(EXAMPLE_IMAGE_PATH)
    output_dir = CACHE_DIR_PATH / "debug_speech_bubbles"
    saved = save_bubble_images(result.blocks, output_dir=output_dir)
    print(f"Saved {len(saved)} images to {output_dir}")


if __name__ == "__main__":
    main()
