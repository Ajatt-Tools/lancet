# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
import pathlib

from lancet.text_detector_client.text_detector_base import SpeechBubbleBlock


def class_name(obj: object) -> str:
    """Return the class name of the given object, typically used for exception formatting."""
    return obj.__class__.__name__


def round_to_stride(value: int, stride: int = 64) -> int:
    """Round to the nearest multiple of stride."""
    return round(value / stride) * stride


def save_bubble_images(blocks: list[SpeechBubbleBlock], *, output_dir: pathlib.Path) -> list[pathlib.Path]:
    """Save all detected line-crop images to the output directory and return their paths."""
    output_dir.mkdir(parents=True, exist_ok=True)
    saved: list[pathlib.Path] = []
    for blk_idx, block in enumerate(blocks):
        box_path = output_dir / f"block_{blk_idx}_box.png"
        block.box_image.save(box_path)
        saved.append(box_path)
        for line_idx, line_images in enumerate(block.lines):
            for chunk_idx, img in enumerate(line_images):
                path = output_dir / f"block_{blk_idx}_line_{line_idx}_chunk_{chunk_idx}.png"
                img.save(path)
                saved.append(path)
    return saved
