# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import typing
from unittest.mock import patch

import pytest

from lancet.ocr.manga_ocr import MangaOcr, adjust_error_message


class ImproveErrorScenario(typing.NamedTuple):
    """A scenario for testing adjust_error_message with a specific OSError pattern."""

    oserror: OSError
    model_name: str
    expected_substring: str


IMPROVE_ERROR_SCENARIOS: dict[str, ImproveErrorScenario] = {
    "vocabulary": ImproveErrorScenario(
        oserror=OSError("Unable to load vocabulary from file"),
        model_name="good/model",
        expected_substring="fugashi/unidic_lite",
    ),
    "preprocessor_config": ImproveErrorScenario(
        oserror=OSError("Can't load image processor for 'bad/model' -- preprocessor_config.json not found"),
        model_name="bad/model",
        expected_substring="not a compatible HuggingFace transformers model",
    ),
    "image_processor": ImproveErrorScenario(
        oserror=OSError("Can't load image processor for 'bad/model'"),
        model_name="bad/model",
        expected_substring="not a compatible HuggingFace transformers model",
    ),
    "not_valid_identifier": ImproveErrorScenario(
        oserror=OSError("'bad/model' is not a valid model identifier listed on 'https://huggingface.co/models'"),
        model_name="bad/model",
        expected_substring="was not found on HuggingFace Hub",
    ),
    "couldnt_find": ImproveErrorScenario(
        oserror=OSError(
            "Couldn't find 'bad/model' in the HuggingFace Hub. If you were trying to load it from "
            "'https://huggingface.co/models', make sure you don't have a local directory with the same name."
        ),
        model_name="bad/model",
        expected_substring="was not found on HuggingFace Hub",
    ),
    "connection_error": ImproveErrorScenario(
        oserror=OSError("Couldn't connect to https://huggingface.co -- ConnectionError"),
        model_name="good/model",
        expected_substring="Cannot reach HuggingFace Hub",
    ),
    "offline": ImproveErrorScenario(
        oserror=OSError("You are in offline mode."),
        model_name="good/model",
        expected_substring="Cannot reach HuggingFace Hub",
    ),
    "unrecognized_passthrough": ImproveErrorScenario(
        oserror=OSError("Something unexpected happened"),
        model_name="good/model",
        expected_substring="Something unexpected happened",
    ),
}


class TestAdjustErrorMessage:
    """Tests for the adjust_error_message helper that translates HuggingFace OSError messages."""

    @pytest.mark.parametrize("scenario", IMPROVE_ERROR_SCENARIOS.values(), ids=IMPROVE_ERROR_SCENARIOS.keys())
    def test_improves_known_patterns(self, scenario: ImproveErrorScenario) -> None:
        result = adjust_error_message(scenario.oserror, scenario.model_name)
        assert isinstance(result, OSError)
        assert scenario.expected_substring in str(result)


class TestTryLoadModelWithWebDownload:
    """Tests that _try_load_model_with_web_download_enabled raises improved error messages."""

    def test_raises_improved_error_for_unsupported_format(self) -> None:
        mocr = object.__new__(MangaOcr)
        with patch.object(mocr, "_load_from_pretrained", side_effect=OSError("Can't load image processor")):
            with pytest.raises(OSError) as excinfo:
                mocr._try_load_model_with_web_download_enabled("tflite/model")
            assert "not a compatible HuggingFace transformers model" in str(excinfo.value)

    def test_raises_improved_error_for_vocabulary(self) -> None:
        mocr = object.__new__(MangaOcr)
        with patch.object(mocr, "_load_from_pretrained", side_effect=OSError("Unable to load vocabulary")):
            with pytest.raises(OSError) as excinfo:
                mocr._try_load_model_with_web_download_enabled("good/model")
            assert "fugashi/unidic_lite" in str(excinfo.value)

    def test_passes_through_unrecognized_error(self) -> None:
        mocr = object.__new__(MangaOcr)
        original = OSError("Something weird happened")
        with patch.object(mocr, "_load_from_pretrained", side_effect=original):
            with pytest.raises(OSError) as excinfo:
                mocr._try_load_model_with_web_download_enabled("good/model")
            assert str(excinfo.value) == str(original)
