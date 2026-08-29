# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""
Tests for the pure helpers in lancet.text_detector_client.text_detector.
"""

import pathlib
import typing

import cv2
import numpy as np
import pytest
from PIL import Image

from lancet.text_detector_client.text_detector import (
    crop_box_region,
    pil_image_to_bgr_array,
    read_image_from_path,
    text_detector_load_error_message,
)
from lancet.text_detector_client.text_detector_base import (
    ComicTextDetectorException,
    Rect,
    clamp,
)


class LoadErrorScenario(typing.NamedTuple):
    """A detector-load exception and its expected rendered prefix."""

    error: Exception
    expected_prefix: str


LOAD_ERROR_SCENARIOS: dict[str, LoadErrorScenario] = {
    "runtime_error": LoadErrorScenario(RuntimeError("load failed"), "RuntimeError: load failed."),
    "os_error": LoadErrorScenario(OSError("device unavailable"), "OSError: device unavailable."),
}


class TestTextDetectorLoadErrorMessage:
    """Test actionable detector-load reporting without automatic cache deletion."""

    @pytest.mark.parametrize("scenario", LOAD_ERROR_SCENARIOS.values(), ids=LOAD_ERROR_SCENARIOS.keys())
    def test_message_preserves_cache(self, scenario: LoadErrorScenario, tmp_path: pathlib.Path) -> None:
        """The message identifies the failure and reset steps while leaving the cache untouched."""
        model_path = tmp_path / "comictextdetector.pt"
        model_path.write_bytes(b"validated checkpoint")
        expected = (
            f"{scenario.expected_prefix} If the problem persists, remove the cached checkpoint at {str(model_path)!r} "
            "and restart Lancet to download it again."
        )

        assert text_detector_load_error_message(model_path, scenario.error) == expected
        assert model_path.read_bytes() == b"validated checkpoint"


class PilToBgrScenario(typing.NamedTuple):
    """A scenario describing a single-pixel RGB image and the expected BGR triplet."""

    rgb: tuple[int, int, int]
    expected_bgr: tuple[int, int, int]


PIL_TO_BGR_SCENARIOS: dict[str, PilToBgrScenario] = {
    "red_pixel": PilToBgrScenario(rgb=(255, 0, 0), expected_bgr=(0, 0, 255)),
    "green_pixel": PilToBgrScenario(rgb=(0, 255, 0), expected_bgr=(0, 255, 0)),
    "blue_pixel": PilToBgrScenario(rgb=(0, 0, 255), expected_bgr=(255, 0, 0)),
    "grey_pixel": PilToBgrScenario(rgb=(128, 128, 128), expected_bgr=(128, 128, 128)),
}


class TestPilImageToBgrArray:
    """pil_image_to_bgr_array converts PIL RGB images into OpenCV-shaped BGR uint8 arrays."""

    @pytest.mark.parametrize("scenario", PIL_TO_BGR_SCENARIOS.values(), ids=PIL_TO_BGR_SCENARIOS.keys())
    def test_pixel_channel_order(self, scenario: PilToBgrScenario) -> None:
        """A 1x1 RGB image converts to a 1x1x3 BGR array with channel order swapped."""
        image = Image.new("RGB", (1, 1), color=scenario.rgb)

        result = pil_image_to_bgr_array(image)

        assert result.shape == (1, 1, 3)
        assert result.dtype == np.uint8
        assert tuple(int(v) for v in result[0, 0]) == scenario.expected_bgr

    def test_larger_image_shape_preserved(self) -> None:
        """A 4x6 RGB image converts to a (6, 4, 3) BGR array (PIL is W,H; numpy is H,W)."""
        image = Image.new("RGB", (4, 6), color=(10, 20, 30))
        result = pil_image_to_bgr_array(image)
        assert result.shape == (6, 4, 3)


def make_solid_bgr_array(height: int, width: int, bgr: tuple[int, int, int]) -> np.ndarray:
    """Build an HxWx3 BGR uint8 numpy array filled with a single color."""
    arr = np.zeros((height, width, 3), dtype=np.uint8)
    arr[:, :] = bgr
    return arr


class CropScenario(typing.NamedTuple):
    """A scenario for crop_box_region that selects a sub-rectangle from a small synthetic image."""

    img_height: int
    img_width: int
    img_bgr: tuple[int, int, int]
    rect: Rect
    expected_size_w_h: tuple[int, int]
    expected_rgb: tuple[int, int, int]


CROP_SCENARIOS: dict[str, CropScenario] = {
    "full_image": CropScenario(
        img_height=4,
        img_width=4,
        img_bgr=(10, 20, 30),  # BGR
        rect=Rect(0, 0, 4, 4),
        expected_size_w_h=(4, 4),
        expected_rgb=(30, 20, 10),  # BGR -> RGB swap
    ),
    "top_left_quadrant": CropScenario(
        img_height=8,
        img_width=8,
        img_bgr=(0, 128, 255),  # BGR for orange-ish
        rect=Rect(0, 0, 4, 4),
        expected_size_w_h=(4, 4),
        expected_rgb=(255, 128, 0),  # RGB
    ),
    "bottom_right_quadrant": CropScenario(
        img_height=8,
        img_width=8,
        img_bgr=(50, 60, 70),
        rect=Rect(4, 4, 8, 8),
        expected_size_w_h=(4, 4),
        expected_rgb=(70, 60, 50),
    ),
}


class TestCropBoxRegion:
    """crop_box_region slices a Rect from a BGR image and returns a PIL RGB image."""

    @pytest.mark.parametrize("scenario", CROP_SCENARIOS.values(), ids=CROP_SCENARIOS.keys())
    def test_size_and_pixel(self, scenario: CropScenario) -> None:
        """The crop has the rect's width/height and the expected RGB pixel everywhere."""
        img = make_solid_bgr_array(scenario.img_height, scenario.img_width, scenario.img_bgr)

        result = crop_box_region(img, scenario.rect)

        assert isinstance(result, Image.Image)
        assert result.size == scenario.expected_size_w_h
        assert result.getpixel((0, 0)) == scenario.expected_rgb


def write_png(path: pathlib.Path, height: int, width: int, bgr: tuple[int, int, int]) -> None:
    """Write a small solid-color PNG at path using cv2 (round-trip-compatible with read_image_from_path)."""
    img = make_solid_bgr_array(height, width, bgr)
    encoded_ok, buffer = cv2.imencode(".png", img)
    assert encoded_ok, "failed to encode test PNG"
    buffer.tofile(str(path))


class TestReadImageFromPath:
    """read_image_from_path round-trips PNGs and raises ComicTextDetectorException on garbage."""

    def test_round_trip_png(self, tmp_path: pathlib.Path) -> None:
        """A small PNG written by cv2 is read back with the expected shape and pixel values."""
        png_path = tmp_path / "probe.png"
        write_png(png_path, height=3, width=5, bgr=(100, 110, 120))

        result = read_image_from_path(png_path)

        assert result.shape == (3, 5, 3)
        assert result.dtype == np.uint8
        assert tuple(int(v) for v in result[0, 0]) == (100, 110, 120)

    def test_undecodable_bytes_raise(self, tmp_path: pathlib.Path) -> None:
        """A file with non-image content makes cv2.imdecode return None, which raises ComicTextDetectorException."""
        garbage = tmp_path / "garbage.png"
        garbage.write_bytes(b"this is not a png file at all, just some text")

        with pytest.raises(ComicTextDetectorException) as excinfo:
            read_image_from_path(garbage)
        assert "Failed to read image" in str(excinfo.value)

    def test_missing_file_raises_file_not_found(self, tmp_path: pathlib.Path) -> None:
        """A nonexistent path raises FileNotFoundError (np.fromfile's behavior, not the function's contract)."""
        missing = tmp_path / "does_not_exist.png"
        with pytest.raises(FileNotFoundError):
            read_image_from_path(missing)


class EmptyImageScenario(typing.NamedTuple):
    """A scenario describing a PIL image that should be rejected by pil_image_to_bgr_array."""

    image: Image.Image
    description: str


EMPTY_IMAGE_SCENARIOS: dict[str, EmptyImageScenario] = {
    "zero_width": EmptyImageScenario(
        image=Image.new("RGB", (0, 4)),
        description="zero-width image",
    ),
    "zero_height": EmptyImageScenario(
        image=Image.new("RGB", (4, 0)),
        description="zero-height image",
    ),
    "zero_both": EmptyImageScenario(
        image=Image.new("RGB", (0, 0)),
        description="zero-width and zero-height image",
    ),
}


class TestPilImageToBgrArrayRejectsEmpty:
    """pil_image_to_bgr_array raises ComicTextDetectorException for empty PIL images."""

    @pytest.mark.parametrize("scenario", EMPTY_IMAGE_SCENARIOS.values(), ids=EMPTY_IMAGE_SCENARIOS.keys())
    def test_empty_image_raises(self, scenario: EmptyImageScenario) -> None:
        """An image with zero width or height raises ComicTextDetectorException."""
        with pytest.raises(ComicTextDetectorException, match="cannot convert an empty PIL image"):
            pil_image_to_bgr_array(scenario.image)


class EmptyCropScenario(typing.NamedTuple):
    """A scenario where crop_box_region receives a degenerate Rect that produces an empty slice."""

    rect: Rect
    description: str


EMPTY_CROP_SCENARIOS: dict[str, EmptyCropScenario] = {
    "zero_width_rect": EmptyCropScenario(
        rect=Rect(2, 0, 2, 4),
        description="x1 == x2 gives zero-width crop",
    ),
    "zero_height_rect": EmptyCropScenario(
        rect=Rect(0, 3, 4, 3),
        description="y1 == y2 gives zero-height crop",
    ),
    "inverted_x": EmptyCropScenario(
        rect=Rect(4, 0, 2, 4),
        description="x1 > x2 gives zero-width crop",
    ),
    "inverted_y": EmptyCropScenario(
        rect=Rect(0, 4, 4, 2),
        description="y1 > y2 gives zero-height crop",
    ),
}


class TestCropBoxRegionRejectsEmpty:
    """crop_box_region raises ComicTextDetectorException for degenerate rectangles."""

    @pytest.mark.parametrize("scenario", EMPTY_CROP_SCENARIOS.values(), ids=EMPTY_CROP_SCENARIOS.keys())
    def test_degenerate_rect_raises(self, scenario: EmptyCropScenario) -> None:
        """A Rect with zero or negative area raises ComicTextDetectorException."""
        img = make_solid_bgr_array(8, 8, (100, 100, 100))
        with pytest.raises(ComicTextDetectorException, match="crop region is empty"):
            crop_box_region(img, scenario.rect)


class HasAreaScenario(typing.NamedTuple):
    """A scenario for Rect.has_area() with the expected boolean result."""

    rect: Rect
    expected: bool


HAS_AREA_SCENARIOS: dict[str, HasAreaScenario] = {
    "normal": HasAreaScenario(rect=Rect(0, 0, 10, 10), expected=True),
    "single_pixel": HasAreaScenario(rect=Rect(5, 5, 6, 6), expected=True),
    "zero_width": HasAreaScenario(rect=Rect(3, 0, 3, 5), expected=False),
    "zero_height": HasAreaScenario(rect=Rect(0, 3, 5, 3), expected=False),
    "inverted_x": HasAreaScenario(rect=Rect(10, 0, 5, 5), expected=False),
    "inverted_y": HasAreaScenario(rect=Rect(0, 10, 5, 5), expected=False),
    "both_zero": HasAreaScenario(rect=Rect(0, 0, 0, 0), expected=False),
    "point": HasAreaScenario(rect=Rect(7, 7, 7, 7), expected=False),
}


class TestRectHasArea:
    """Rect.has_area() returns True only when the rectangle has positive width and height."""

    @pytest.mark.parametrize("scenario", HAS_AREA_SCENARIOS.values(), ids=HAS_AREA_SCENARIOS.keys())
    def test_has_area(self, scenario: HasAreaScenario) -> None:
        """Each scenario asserts has_area() returns the expected boolean."""
        assert scenario.rect.has_area() is scenario.expected


class ClampScenario(typing.NamedTuple):
    """A scenario for the clamp helper."""

    min_val: int
    val: int
    max_val: int
    expected: int


CLAMP_SCENARIOS: dict[str, ClampScenario] = {
    "within_range": ClampScenario(min_val=0, val=5, max_val=10, expected=5),
    "at_min": ClampScenario(min_val=0, val=0, max_val=10, expected=0),
    "at_max": ClampScenario(min_val=0, val=10, max_val=10, expected=10),
    "below_min": ClampScenario(min_val=0, val=-3, max_val=10, expected=0),
    "above_max": ClampScenario(min_val=0, val=15, max_val=10, expected=10),
    "negative_range": ClampScenario(min_val=-10, val=-5, max_val=-1, expected=-5),
}


class TestClamp:
    """clamp clamps a value to [min_val, max_val]."""

    @pytest.mark.parametrize("scenario", CLAMP_SCENARIOS.values(), ids=CLAMP_SCENARIOS.keys())
    def test_clamp(self, scenario: ClampScenario) -> None:
        """Each scenario asserts clamp returns the expected value."""
        assert clamp(scenario.min_val, scenario.val, scenario.max_val) == scenario.expected


class RectClampScenario(typing.NamedTuple):
    """A scenario for Rect.clamp() with given image dimensions and expected result."""

    rect: Rect
    img_width: int
    img_height: int
    expected: Rect
    expected_has_area: bool


RECT_CLAMP_SCENARIOS: dict[str, RectClampScenario] = {
    "already_inside": RectClampScenario(
        rect=Rect(10, 20, 100, 200),
        img_width=640,
        img_height=480,
        expected=Rect(10, 20, 100, 200),
        expected_has_area=True,
    ),
    "negative_x1": RectClampScenario(
        rect=Rect(-1, 485, 686, 550),
        img_width=690,
        img_height=554,
        expected=Rect(0, 485, 686, 550),
        expected_has_area=True,
    ),
    "exceeds_width": RectClampScenario(
        rect=Rect(600, 0, 700, 100),
        img_width=640,
        img_height=480,
        expected=Rect(600, 0, 640, 100),
        expected_has_area=True,
    ),
    "exceeds_height": RectClampScenario(
        rect=Rect(0, 400, 100, 500),
        img_width=640,
        img_height=480,
        expected=Rect(0, 400, 100, 480),
        expected_has_area=True,
    ),
    "fully_outside_negative": RectClampScenario(
        rect=Rect(-50, -30, -10, -5),
        img_width=640,
        img_height=480,
        expected=Rect(0, 0, 0, 0),
        expected_has_area=False,
    ),
    "fully_outside_positive": RectClampScenario(
        rect=Rect(700, 500, 800, 600),
        img_width=640,
        img_height=480,
        expected=Rect(640, 480, 640, 480),
        expected_has_area=False,
    ),
    "negative_both_corners": RectClampScenario(
        rect=Rect(-10, -20, 50, 60),
        img_width=100,
        img_height=100,
        expected=Rect(0, 0, 50, 60),
        expected_has_area=True,
    ),
}


class TestRectClamp:
    """Rect.clamp() trims coordinates to image bounds."""

    @pytest.mark.parametrize("scenario", RECT_CLAMP_SCENARIOS.values(), ids=RECT_CLAMP_SCENARIOS.keys())
    def test_clamped_rect(self, scenario: RectClampScenario) -> None:
        """Each scenario asserts clamp() returns the expected Rect."""
        result = scenario.rect.clamp(img_width=scenario.img_width, img_height=scenario.img_height)
        assert result == scenario.expected
        assert result.has_area() is scenario.expected_has_area
