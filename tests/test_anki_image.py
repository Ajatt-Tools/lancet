# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Tests for resizing, validating, and encoding Anki attachment images."""

import io
import typing
from unittest.mock import call, create_autospec

import pytest
from PIL import Image, features

from lancet.anki.image import encode_image, resize_image
from lancet.anki.image_types import AnkiImageFormat, ImageParameters
from lancet.exceptions import AnkiImageEncodingError

ENCODING_SETTINGS = ImageParameters(width=0, height=250, quality=33)


class ResizeScenario(typing.NamedTuple):
    """Source dimensions, settings, and expected resized dimensions."""

    source_size: tuple[int, int]
    settings: ImageParameters
    expected_size: tuple[int, int]


RESIZE_SCENARIOS: dict[str, ResizeScenario] = {
    "height_bound": ResizeScenario(
        source_size=(1_000, 500), settings=ImageParameters(width=0, height=200, quality=33), expected_size=(400, 200)
    ),
    "width_bound": ResizeScenario(
        source_size=(1_000, 500), settings=ImageParameters(width=300, height=0, quality=33), expected_size=(300, 150)
    ),
    "two_bounds": ResizeScenario(
        source_size=(1_000, 500), settings=ImageParameters(width=300, height=100, quality=33), expected_size=(200, 100)
    ),
    "unconstrained": ResizeScenario(
        source_size=(1_000, 500), settings=ImageParameters(width=0, height=0, quality=33), expected_size=(1_000, 500)
    ),
    "never_upscale": ResizeScenario(
        source_size=(100, 50), settings=ImageParameters(width=300, height=300, quality=33), expected_size=(100, 50)
    ),
}


class EncodingScenario(typing.NamedTuple):
    """A configured container and the fully decoded image expected from it."""

    image_format: AnkiImageFormat
    pillow_format: str
    expected_size: tuple[int, int]


ENCODING_SCENARIOS: dict[str, EncodingScenario] = {
    "webp": EncodingScenario(image_format=AnkiImageFormat.webp, pillow_format="WEBP", expected_size=(250, 250)),
    "avif": EncodingScenario(image_format=AnkiImageFormat.avif, pillow_format="AVIF", expected_size=(250, 250)),
}


class UnsupportedCodecScenario(typing.NamedTuple):
    """A configured codec that Pillow reports as unavailable."""

    image_format: AnkiImageFormat
    expected_message: str


UNSUPPORTED_CODEC_SCENARIOS: dict[str, UnsupportedCodecScenario] = {
    "webp": UnsupportedCodecScenario(
        image_format=AnkiImageFormat.webp,
        expected_message="Pillow does not support WEBP image encoding",
    ),
    "avif": UnsupportedCodecScenario(
        image_format=AnkiImageFormat.avif,
        expected_message="Pillow does not support AVIF image encoding",
    ),
}


class InvalidParametersScenario(typing.NamedTuple):
    """Invalid image settings and the public validation error expected from encoding."""

    settings: ImageParameters
    expected_message: str


INVALID_PARAMETERS_SCENARIOS: dict[str, InvalidParametersScenario] = {
    "negative_width": InvalidParametersScenario(
        settings=ImageParameters(width=-1, height=0, quality=33),
        expected_message="Image dimensions cannot be negative",
    ),
    "negative_height": InvalidParametersScenario(
        settings=ImageParameters(width=0, height=-1, quality=33),
        expected_message="Image dimensions cannot be negative",
    ),
    "negative_quality": InvalidParametersScenario(
        settings=ImageParameters(width=0, height=0, quality=-1),
        expected_message="Image quality must be between 0 and 100",
    ),
    "quality_above_maximum": InvalidParametersScenario(
        settings=ImageParameters(width=0, height=0, quality=101),
        expected_message="Image quality must be between 0 and 100",
    ),
}


class EncodingFailureScenario(typing.NamedTuple):
    """A Pillow save failure and the wrapped public image-encoding error."""

    image_format: AnkiImageFormat
    error_type: type[OSError] | type[ValueError]
    error_message: str
    expected_message: str


ENCODING_FAILURE_SCENARIOS: dict[str, EncodingFailureScenario] = {
    "webp_os_error": EncodingFailureScenario(
        image_format=AnkiImageFormat.webp,
        error_type=OSError,
        error_message="encoder failed",
        expected_message="Could not encode WEBP image: encoder failed",
    ),
    "avif_value_error": EncodingFailureScenario(
        image_format=AnkiImageFormat.avif,
        error_type=ValueError,
        error_message="encoder failed",
        expected_message="Could not encode AVIF image: encoder failed",
    ),
}


class TestResizeImage:
    """Test Pillow resize behavior used for Anki attachments."""

    @pytest.mark.parametrize("scenario", RESIZE_SCENARIOS.values(), ids=RESIZE_SCENARIOS.keys())
    def test_resizes_with_maximum_bounds(self, scenario: ResizeScenario) -> None:
        """Dimensions preserve aspect ratio and never enlarge the selected image."""
        image = Image.new("RGB", scenario.source_size)
        assert resize_image(image, scenario.settings).size == scenario.expected_size


class TestEncodeImage:
    """Test in-memory Pillow encoding for Anki media."""

    @pytest.mark.parametrize("scenario", ENCODING_SCENARIOS.values(), ids=ENCODING_SCENARIOS.keys())
    def test_encodes_supported_format(self, scenario: EncodingScenario) -> None:
        """Encoding produces a fully decodable, resized RGB image in the requested container."""
        encoded = encode_image(
            Image.new("RGB", (500, 500)), image_format=scenario.image_format, settings=ENCODING_SETTINGS
        )
        decoded = Image.open(io.BytesIO(encoded.data))
        decoded.load()
        assert decoded.format == scenario.pillow_format
        assert decoded.mode == "RGB"
        assert decoded.size == scenario.expected_size
        assert encoded.image_format == scenario.image_format
        assert encoded.settings == ENCODING_SETTINGS

    @pytest.mark.parametrize("scenario", UNSUPPORTED_CODEC_SCENARIOS.values(), ids=UNSUPPORTED_CODEC_SCENARIOS.keys())
    def test_rejects_unsupported_codec(
        self, scenario: UnsupportedCodecScenario, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An unavailable configured codec raises instead of silently changing output format."""
        check = create_autospec(features.check, return_value=False)
        monkeypatch.setattr("lancet.anki.image.features.check", check)
        with pytest.raises(AnkiImageEncodingError) as exc_info:
            encode_image(Image.new("RGB", (100, 100)), image_format=scenario.image_format, settings=ENCODING_SETTINGS)
        assert str(exc_info.value) == scenario.expected_message
        assert check.call_args == call(scenario.image_format.value)

    @pytest.mark.parametrize("scenario", INVALID_PARAMETERS_SCENARIOS.values(), ids=INVALID_PARAMETERS_SCENARIOS.keys())
    def test_rejects_invalid_parameters(self, scenario: InvalidParametersScenario) -> None:
        """Invalid dimensions and quality values fail before Pillow encoding begins."""
        with pytest.raises(AnkiImageEncodingError) as exc_info:
            encode_image(Image.new("RGB", (100, 100)), image_format=AnkiImageFormat.webp, settings=scenario.settings)
        assert str(exc_info.value) == scenario.expected_message

    @pytest.mark.parametrize("scenario", ENCODING_FAILURE_SCENARIOS.values(), ids=ENCODING_FAILURE_SCENARIOS.keys())
    def test_wraps_pillow_encoding_errors(
        self, scenario: EncodingFailureScenario, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Pillow failures become exact public errors while retaining their cause identity."""
        image = Image.new("RGB", (100, 100))
        pillow_error = scenario.error_type(scenario.error_message)
        resized = create_autospec(Image.Image, instance=True)
        resized.save.side_effect = pillow_error
        check = create_autospec(features.check, return_value=True)
        resize = create_autospec(resize_image, return_value=resized)
        monkeypatch.setattr("lancet.anki.image.features.check", check)
        monkeypatch.setattr("lancet.anki.image.resize_image", resize)

        with pytest.raises(AnkiImageEncodingError) as exc_info:
            encode_image(image, image_format=scenario.image_format, settings=ENCODING_SETTINGS)

        assert str(exc_info.value) == scenario.expected_message
        assert exc_info.value.__cause__ is pillow_error
        assert check.call_args == call(scenario.image_format.value)
        assert resize.call_args == call(image, ENCODING_SETTINGS)
