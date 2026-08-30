# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import typing
from collections.abc import Sequence
from unittest.mock import create_autospec, patch

import pytest
from transformers import PreTrainedTokenizerBase

from lancet.ocr.error_messages import (
    adjust_auto_tokenizer_error_message,
    adjust_error_message,
    adjust_slow_tokenizer_error_message,
)
from lancet.ocr.manga_ocr import (
    MangaOcr,
    load_tokenizer,
    tokenizer_is_fast_label,
)
from lancet.ocr.manga_ocr_base import (
    MangaOCRLoadError,
    MangaOCRTokenizerLoadError,
)


class FakeTokenizer(PreTrainedTokenizerBase):
    """Minimal tokenizer instance used to satisfy load_tokenizer's runtime return type check."""

    @property
    def is_fast(self) -> bool:
        """Return whether this fake tokenizer represents a fast tokenizer."""
        return False


class TokenizerWithoutIsFast(PreTrainedTokenizerBase):
    """Minimal tokenizer that does not define is_fast."""

    pass


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


class WebLoadErrorScenario(typing.NamedTuple):
    """A web-enabled model load failure and its exact public error contract."""

    error_message: str
    model_name: str
    expected_message: str
    preserve_identity: bool = False


WEB_LOAD_ERROR_SCENARIOS: dict[str, WebLoadErrorScenario] = {
    "unsupported_format": WebLoadErrorScenario(
        "Can't load image processor",
        "tflite/model",
        "'tflite/model' is not a compatible HuggingFace transformers model. "
        "It may be in TFLite, ONNX, or another unsupported format. "
        "Lancet supports safetensors models like 'tatsumoto/manga-ocr-base' or "
        "'jzhang533/manga-ocr-base-2025'.",
    ),
    "missing_vocabulary": WebLoadErrorScenario(
        "Unable to load vocabulary",
        "good/model",
        "Unable to load vocabulary. This may indicate missing files for fugashi/unidic_lite "
        "(commonly happens in PyInstaller builds).",
    ),
    "unrecognized_passthrough": WebLoadErrorScenario(
        "Something weird happened", "good/model", "Something weird happened", True
    ),
}


class TestTryLoadModelWithWebDownload:
    """Tests that _try_load_model_with_web_download_enabled raises improved error messages."""

    @pytest.mark.parametrize("scenario", WEB_LOAD_ERROR_SCENARIOS.values(), ids=WEB_LOAD_ERROR_SCENARIOS.keys())
    def test_normalizes_load_error(self, scenario: WebLoadErrorScenario) -> None:
        """Known download failures are improved while unknown errors retain their message."""
        mocr = create_autospec(MangaOcr, instance=True, spec_set=True)
        error = OSError(scenario.error_message)
        mocr._load_from_pretrained.side_effect = error
        with pytest.raises(OSError) as excinfo:
            MangaOcr._try_load_model_with_web_download_enabled(mocr, scenario.model_name)
        assert str(excinfo.value) == scenario.expected_message
        if scenario.preserve_identity:
            assert excinfo.value is error


class TestLoadModelRetry:
    """_load_model warns on a local cache miss and then retries with downloads enabled."""

    @pytest.mark.parametrize(
        "error_message,model_name",
        [("cache miss", "model/name"), ("offline cache", "alternate/model")],
        ids=["cache_miss", "offline_cache"],
    )
    def test_local_cache_failure_warns_then_retries_with_downloads(self, error_message: str, model_name: str) -> None:
        """A local cache miss logs a warning before the download-enabled retry."""
        mocr = create_autospec(MangaOcr, instance=True, spec_set=True)
        with (patch("lancet.ocr.manga_ocr.logger.warning") as mock_warning,):
            mocr._load_from_pretrained.side_effect = OSError(error_message)
            MangaOcr._load_model(mocr, model_name)

            assert mocr._load_from_pretrained.call_count == 1
            mocr._try_load_model_with_web_download_enabled.assert_called_once_with(model_name)
            assert mock_warning.call_args.args == (
                f"Failed to load OCR model from local cache: OSError: {error_message}. "
                "Retrying with downloads enabled.",
            )


class AutoTokenizerErrorScenario(typing.NamedTuple):
    """A scenario for improving AutoTokenizer load errors."""

    error: Exception
    expected_substrings: Sequence[str]


AUTO_TOKENIZER_ERROR_SCENARIOS: dict[str, AutoTokenizerErrorScenario] = {
    "backend_tokenizer_error": AutoTokenizerErrorScenario(
        error=ValueError("Couldn't instantiate the backend tokenizer from one of:"),
        expected_substrings=("tokenizer.json", "cached snapshot", "~/.cache/huggingface/hub/"),
    ),
    "generic_tokenizer_error": AutoTokenizerErrorScenario(
        error=ValueError("unexpected auto failure"),
        expected_substrings=("AutoTokenizer failed", "unexpected auto failure"),
    ),
}


class TestAdjustAutoTokenizerErrorMessage:
    """adjust_auto_tokenizer_error_message returns actionable AutoTokenizer load errors."""

    @pytest.mark.parametrize(
        "scenario", AUTO_TOKENIZER_ERROR_SCENARIOS.values(), ids=AUTO_TOKENIZER_ERROR_SCENARIOS.keys()
    )
    def test_adjusts_auto_tokenizer_error(self, scenario: AutoTokenizerErrorScenario) -> None:
        result = adjust_auto_tokenizer_error_message(scenario.error, "tatsumoto/manga-ocr-base")

        assert isinstance(result, MangaOCRTokenizerLoadError)
        assert all(substring in str(result) for substring in scenario.expected_substrings)


class SlowTokenizerErrorScenario(typing.NamedTuple):
    """A scenario for improving BertJapaneseTokenizer fallback load errors."""

    error: Exception
    expected_substrings: Sequence[str]


SLOW_TOKENIZER_ERROR_SCENARIOS: dict[str, SlowTokenizerErrorScenario] = {
    "japanese_dependency_error": SlowTokenizerErrorScenario(
        error=ImportError("No module named fugashi"),
        expected_substrings=("BertJapaneseTokenizer fallback failed", "fugashi/unidic_lite"),
    ),
    "generic_slow_tokenizer_error": SlowTokenizerErrorScenario(
        error=ValueError("unexpected slow failure"),
        expected_substrings=("BertJapaneseTokenizer fallback failed", "unexpected slow failure"),
    ),
}


class TestAdjustSlowTokenizerErrorMessage:
    """adjust_slow_tokenizer_error_message returns actionable slow-tokenizer load errors."""

    @pytest.mark.parametrize(
        "scenario", SLOW_TOKENIZER_ERROR_SCENARIOS.values(), ids=SLOW_TOKENIZER_ERROR_SCENARIOS.keys()
    )
    def test_adjusts_slow_tokenizer_error(self, scenario: SlowTokenizerErrorScenario) -> None:
        result = adjust_slow_tokenizer_error_message(scenario.error, "tatsumoto/manga-ocr-base")

        assert isinstance(result, MangaOCRTokenizerLoadError)
        assert all(substring in str(result) for substring in scenario.expected_substrings)


class TestTokenizerIsFastLabel:
    """tokenizer_is_fast_label is safe for logging regardless of tokenizer attributes."""

    @pytest.mark.parametrize(
        "tokenizer,expected",
        [
            (FakeTokenizer(), "False"),
            (TokenizerWithoutIsFast(), "unknown"),
        ],
    )
    def test_label(self, tokenizer: object, expected: str) -> None:
        assert tokenizer_is_fast_label(tokenizer) == expected


class TokenizerFallbackScenario(typing.NamedTuple):
    """A scenario for testing the fast→slow tokenizer fallback."""

    fast_side_effect: object
    slow_side_effect: object
    expected_auto_call_count: int
    expected_slow_call_count: int
    should_raise: bool
    expected_log_substring: str


TOKENIZER_FALLBACK_SCENARIOS: dict[str, TokenizerFallbackScenario] = {
    "fast_succeeds": TokenizerFallbackScenario(
        fast_side_effect=FakeTokenizer(),
        slow_side_effect=FakeTokenizer(),
        expected_auto_call_count=1,
        expected_slow_call_count=0,
        should_raise=False,
        expected_log_substring="Loaded tokenizer via AutoTokenizer",
    ),
    "falls_back_on_value_error": TokenizerFallbackScenario(
        fast_side_effect=ValueError("no sentencepiece"),
        slow_side_effect=FakeTokenizer(),
        expected_auto_call_count=1,
        expected_slow_call_count=1,
        should_raise=False,
        expected_log_substring="Loaded tokenizer via BertJapaneseTokenizer",
    ),
    "falls_back_on_import_error": TokenizerFallbackScenario(
        fast_side_effect=ImportError("no tokenizers module"),
        slow_side_effect=FakeTokenizer(),
        expected_auto_call_count=1,
        expected_slow_call_count=1,
        should_raise=False,
        expected_log_substring="Loaded tokenizer via BertJapaneseTokenizer",
    ),
    "panics_when_both_fail": TokenizerFallbackScenario(
        fast_side_effect=ValueError("fast broken"),
        slow_side_effect=ValueError("slow broken"),
        expected_auto_call_count=1,
        expected_slow_call_count=1,
        should_raise=True,
        expected_log_substring="BertJapaneseTokenizer fallback failed",
    ),
}


class TestLoadTokenizerFallback:
    """load_tokenizer tries the fast tokenizer first, falling back to slow on failure."""

    @pytest.mark.parametrize("scenario", TOKENIZER_FALLBACK_SCENARIOS.values(), ids=TOKENIZER_FALLBACK_SCENARIOS.keys())
    def test_fallback_behavior(self, scenario: TokenizerFallbackScenario) -> None:
        with (
            patch("lancet.ocr.manga_ocr.AutoTokenizer.from_pretrained") as mock_auto_from_pretrained,
            patch("lancet.ocr.manga_ocr.BertJapaneseTokenizer.from_pretrained") as mock_slow_from_pretrained,
            patch("lancet.ocr.manga_ocr.logger.info") as mock_info,
            patch("lancet.ocr.manga_ocr.logger.warning") as mock_warning,
            patch("lancet.ocr.manga_ocr.logger.error") as mock_error,
        ):
            mock_auto_from_pretrained.side_effect = [scenario.fast_side_effect]
            mock_slow_from_pretrained.side_effect = [scenario.slow_side_effect]
            if scenario.should_raise:
                with pytest.raises(MangaOCRTokenizerLoadError):
                    load_tokenizer("model/name", local_files_only=True)
            else:
                load_tokenizer("model/name", local_files_only=True)
            assert mock_auto_from_pretrained.call_count == scenario.expected_auto_call_count
            assert mock_slow_from_pretrained.call_count == scenario.expected_slow_call_count
            assert scenario.expected_log_substring in " ".join(
                str(call.args[0])
                for call in [*mock_info.call_args_list, *mock_warning.call_args_list, *mock_error.call_args_list]
            )


class MangaOcrInitErrorScenario(typing.NamedTuple):
    """A model-load failure and the public exception MangaOcr should raise."""

    input_error_type: type[Exception]
    input_message: str
    expected_type: type[Exception]
    expected_message: str
    preserve_identity: bool


MANGA_OCR_INIT_ERROR_SCENARIOS: dict[str, MangaOcrInitErrorScenario] = {
    "specific_error_preserved": MangaOcrInitErrorScenario(
        MangaOCRTokenizerLoadError,
        "clean message",
        MangaOCRTokenizerLoadError,
        "clean message",
        True,
    ),
    "generic_error_wrapped": MangaOcrInitErrorScenario(
        RuntimeError,
        "generic failure",
        MangaOCRLoadError,
        "RuntimeError: generic failure",
        False,
    ),
}


class TestMangaOcrInitErrors:
    """MangaOcr.__init__ preserves specific OCR exceptions instead of double-wrapping them."""

    @pytest.mark.parametrize(
        "scenario", MANGA_OCR_INIT_ERROR_SCENARIOS.values(), ids=MANGA_OCR_INIT_ERROR_SCENARIOS.keys()
    )
    def test_load_error(self, scenario: MangaOcrInitErrorScenario) -> None:
        """Specific OCR errors pass through while generic failures are wrapped."""
        error = scenario.input_error_type(scenario.input_message)
        with patch.object(MangaOcr, "_load_model", side_effect=error):
            with pytest.raises(scenario.expected_type) as excinfo:
                MangaOcr()
        assert str(excinfo.value) == scenario.expected_message
        if scenario.preserve_identity:
            assert excinfo.value is error
