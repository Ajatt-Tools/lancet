# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Tests for text-detector helpers, construction, and speech-bubble integration."""

import errno
import pathlib
import re
import typing
from collections.abc import Sequence
from unittest.mock import create_autospec, patch

import cv2
import numpy as np
import pytest
from PIL import Image

from comic_text_detector.inference import TextDetector
from comic_text_detector.utils.textblock import TextBlock
from lancet.model_utils.device import TorchDevice
from lancet.text_detector_client.model_cache import ComicTextDetectorCache
from lancet.text_detector_client.text_detector import (
    ComicTextDetector,
    DetectResult,
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

EMPTY_PIL_IMAGE_RE = re.compile("cannot convert an empty PIL image")
EMPTY_CROP_RE = re.compile("crop region is empty")


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


class DetectorConstructorScenario(typing.NamedTuple):
    """Constructor settings and selected inference device."""

    force_cpu: bool
    detector_input_size: int
    device: TorchDevice


DETECTOR_CONSTRUCTOR_SCENARIOS: dict[str, DetectorConstructorScenario] = {
    "forced_cpu": DetectorConstructorScenario(True, 768, TorchDevice.cpu),
    "automatic_cuda": DetectorConstructorScenario(False, 1024, TorchDevice.cuda),
}


class TestComicTextDetectorConstructor:
    """Test model-path, resolution, and device forwarding during construction."""

    @pytest.mark.parametrize(
        "scenario", DETECTOR_CONSTRUCTOR_SCENARIOS.values(), ids=DETECTOR_CONSTRUCTOR_SCENARIOS.keys()
    )
    def test_builds_backend_once(self, scenario: DetectorConstructorScenario, tmp_path: pathlib.Path) -> None:
        """Load the cached checkpoint once and pass normalized settings to TextDetector."""
        model_path = tmp_path / "comictextdetector.pt"
        cache = create_autospec(ComicTextDetectorCache, instance=True)
        cache.comic_text_detector_path.return_value = model_path
        backend = create_autospec(TextDetector, instance=True)
        backend.device = scenario.device.name

        with (
            patch(
                "lancet.text_detector_client.text_detector.ComicTextDetectorCache",
                autospec=True,
                return_value=cache,
            ) as cache_class,
            patch(
                "lancet.text_detector_client.text_detector.TextDetector", autospec=True, return_value=backend
            ) as detector_class,
            patch(
                "lancet.text_detector_client.text_detector.get_device",
                autospec=True,
                return_value=scenario.device,
            ) as get_device,
        ):
            detector = ComicTextDetector(
                force_cpu=scenario.force_cpu,
                detector_input_size=scenario.detector_input_size,
            )

        assert detector.force_cpu is scenario.force_cpu
        assert detector.detector_input_size == scenario.detector_input_size
        cache_class.assert_called_once_with()
        cache.comic_text_detector_path.assert_called_once_with()
        get_device.assert_called_once_with(force_cpu=scenario.force_cpu)
        detector_class.assert_called_once_with(
            model_path=model_path,
            input_size=scenario.detector_input_size,
            device=scenario.device.name.lower(),
            act="leaky",
        )


DETECTOR_CONSTRUCTOR_ERROR_SCENARIOS: dict[str, Exception] = {
    "runtime_error": RuntimeError("invalid checkpoint"),
    "os_error": OSError("device unavailable"),
}


class TestComicTextDetectorConstructorErrors:
    """Test actionable error normalization without deleting the checkpoint."""

    @pytest.mark.parametrize(
        "error",
        DETECTOR_CONSTRUCTOR_ERROR_SCENARIOS.values(),
        ids=DETECTOR_CONSTRUCTOR_ERROR_SCENARIOS.keys(),
    )
    def test_wraps_backend_failure_and_preserves_cache(self, error: Exception, tmp_path: pathlib.Path) -> None:
        """Wrap the original failure, retain its cause, and preserve the validated file."""
        model_path = tmp_path / "comictextdetector.pt"
        model_path.write_bytes(b"validated checkpoint")
        cache = create_autospec(ComicTextDetectorCache, instance=True)
        cache.comic_text_detector_path.return_value = model_path

        with (
            patch(
                "lancet.text_detector_client.text_detector.ComicTextDetectorCache",
                autospec=True,
                return_value=cache,
            ),
            patch("lancet.text_detector_client.text_detector.TextDetector", autospec=True, side_effect=error),
            patch(
                "lancet.text_detector_client.text_detector.get_device",
                autospec=True,
                return_value=TorchDevice.cpu,
            ),
            pytest.raises(ComicTextDetectorException) as exc_info,
        ):
            ComicTextDetector(force_cpu=True, detector_input_size=512)

        assert str(exc_info.value) == text_detector_load_error_message(model_path, error)
        assert exc_info.value.__cause__ is error
        assert model_path.read_bytes() == b"validated checkpoint"
        cache.comic_text_detector_path.assert_called_once_with()


def make_detector_with_mocked_backend() -> ComicTextDetector:
    """Construct a detector while replacing checkpoint and inference dependencies."""
    cache = create_autospec(ComicTextDetectorCache, instance=True)
    cache.comic_text_detector_path.return_value = pathlib.Path("comictextdetector.pt")
    backend = create_autospec(TextDetector, instance=True)
    backend.device = TorchDevice.cpu.name
    with (
        patch("lancet.text_detector_client.text_detector.ComicTextDetectorCache", return_value=cache),
        patch("lancet.text_detector_client.text_detector.TextDetector", return_value=backend),
        patch("lancet.text_detector_client.text_detector.get_device", return_value=TorchDevice.cpu),
    ):
        return ComicTextDetector(force_cpu=True)


class SpeechBubbleClampScenario(typing.NamedTuple):
    """A detector rectangle and its expected clamped speech-bubble box."""

    xyxy: Sequence[int]
    expected_box: Rect | None


SPEECH_BUBBLE_CLAMP_SCENARIOS: dict[str, SpeechBubbleClampScenario] = {
    "partially_outside_is_clamped": SpeechBubbleClampScenario((-2, -1, 4, 5), Rect(0, 0, 4, 5)),
    "fully_outside_is_skipped": SpeechBubbleClampScenario((12, 1, 14, 3), None),
}


class TestSpeechBubbleClampingIntegration:
    """Test detector rectangles are clamped before speech-bubble crops are created."""

    @pytest.mark.parametrize(
        "scenario", SPEECH_BUBBLE_CLAMP_SCENARIOS.values(), ids=SPEECH_BUBBLE_CLAMP_SCENARIOS.keys()
    )
    def test_clamped_blocks(self, scenario: SpeechBubbleClampScenario) -> None:
        """Partial boxes produce bounded crops while zero-area boxes are omitted."""
        detector = make_detector_with_mocked_backend()
        mask = np.zeros((8, 10), dtype=np.uint8)
        detected = DetectResult(mask=mask, mask_refined=mask, blk_list=[TextBlock(list(scenario.xyxy), font_size=12)])
        with patch.object(detector, "_detect_text", return_value=detected):
            result = detector.get_speech_bubbles(Image.new("RGB", (10, 8)))

        assert [block.box for block in result.blocks] == (
            [] if scenario.expected_box is None else [scenario.expected_box]
        )
        if scenario.expected_box is not None:
            assert result.blocks[0].box_image.size == (
                scenario.expected_box.x2 - scenario.expected_box.x1,
                scenario.expected_box.y2 - scenario.expected_box.y1,
            )


class PilToBgrScenario(typing.NamedTuple):
    """An RGB image size/color and expected BGR triplet."""

    width: int
    height: int
    rgb: tuple[int, int, int]
    expected_bgr: tuple[int, int, int]


PIL_TO_BGR_SCENARIOS: dict[str, PilToBgrScenario] = {
    "red_pixel": PilToBgrScenario(1, 1, (255, 0, 0), (0, 0, 255)),
    "green_pixel": PilToBgrScenario(1, 1, (0, 255, 0), (0, 255, 0)),
    "blue_pixel": PilToBgrScenario(1, 1, (0, 0, 255), (255, 0, 0)),
    "grey_pixel": PilToBgrScenario(1, 1, (128, 128, 128), (128, 128, 128)),
    "larger_image": PilToBgrScenario(4, 6, (10, 20, 30), (30, 20, 10)),
}


class TestPilImageToBgrArray:
    """pil_image_to_bgr_array converts PIL RGB images into OpenCV-shaped BGR uint8 arrays."""

    @pytest.mark.parametrize("scenario", PIL_TO_BGR_SCENARIOS.values(), ids=PIL_TO_BGR_SCENARIOS.keys())
    def test_pixel_channel_order(self, scenario: PilToBgrScenario) -> None:
        """RGB images preserve dimensions and swap pixel channels to BGR."""
        image = Image.new("RGB", (scenario.width, scenario.height), color=scenario.rgb)

        result = pil_image_to_bgr_array(image)

        assert result.shape == (scenario.height, scenario.width, 3)
        assert result.dtype == np.uint8
        assert tuple(int(v) for v in result[0, 0]) == scenario.expected_bgr


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


class ReadImageScenario(typing.NamedTuple):
    """An image-file condition and expected error contract."""

    file_kind: typing.Literal["png", "garbage", "missing"]
    error_type: type[Exception] | None
    expected_message_template: str


READ_IMAGE_SCENARIOS: dict[str, ReadImageScenario] = {
    "png_round_trip": ReadImageScenario("png", None, ""),
    "undecodable_bytes": ReadImageScenario(
        "garbage",
        ComicTextDetectorException,
        "Failed to read image: {path}. Possible cause: Animation file, Corrupted file or Unsupported type",
    ),
    "missing_file": ReadImageScenario("missing", FileNotFoundError, ""),
}


def prepare_image_path(scenario: ReadImageScenario, tmp_path: pathlib.Path) -> pathlib.Path:
    """Create the image fixture requested by scenario and return its path."""
    image_path = tmp_path / "probe.png"
    if scenario.file_kind == "png":
        write_png(image_path, height=3, width=5, bgr=(100, 110, 120))
    elif scenario.file_kind == "garbage":
        image_path.write_bytes(b"this is not a png file at all, just some text")
    return image_path


def assert_image_read_success(image_path: pathlib.Path) -> None:
    """Assert a valid PNG is decoded with its expected shape, type, and pixel."""
    result = read_image_from_path(image_path)
    assert result.shape == (3, 5, 3)
    assert result.dtype == np.uint8
    assert tuple(int(v) for v in result[0, 0]) == (100, 110, 120)


def assert_image_read_error(image_path: pathlib.Path, error_type: type[Exception], expected_message: str) -> None:
    """Assert image_path raises the requested public error contract."""
    with pytest.raises(error_type) as exc_info:
        read_image_from_path(image_path)
    if isinstance(exc_info.value, FileNotFoundError):
        assert exc_info.value.errno == errno.ENOENT
        assert exc_info.value.filename is not None
        assert pathlib.Path(exc_info.value.filename) == image_path
    else:
        assert str(exc_info.value) == expected_message


class TestReadImageFromPath:
    """read_image_from_path round-trips PNGs and raises ComicTextDetectorException on garbage."""

    @pytest.mark.parametrize("scenario", READ_IMAGE_SCENARIOS.values(), ids=READ_IMAGE_SCENARIOS.keys())
    def test_read(self, scenario: ReadImageScenario, tmp_path: pathlib.Path) -> None:
        """Read valid PNG data and preserve the distinct malformed and missing-file errors."""
        image_path = prepare_image_path(scenario, tmp_path)
        if scenario.error_type is None:
            assert_image_read_success(image_path)
        else:
            expected_message = scenario.expected_message_template.format(path=image_path)
            assert_image_read_error(image_path, scenario.error_type, expected_message)


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
        with pytest.raises(ComicTextDetectorException, match=EMPTY_PIL_IMAGE_RE):
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
        with pytest.raises(ComicTextDetectorException, match=EMPTY_CROP_RE):
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
