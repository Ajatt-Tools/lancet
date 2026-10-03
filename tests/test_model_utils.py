# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import pathlib
import typing
from collections.abc import Sequence

import pytest
from PIL import Image

from lancet.model_utils.base import ModelLoadError, ModelLoaderStatus, ModelName
from lancet.model_utils.common import class_name, round_to_stride, save_bubble_images
from lancet.model_utils.ocr_service import deduplicate
from lancet.text_detector_client.text_detector_base import Rect, SpeechBubbleBlock


class RoundToStrideScenario(typing.NamedTuple):
    """A stride-rounding input and expected result."""

    value: int
    stride: int
    expected: int


ROUND_TO_STRIDE_SCENARIOS: dict[str, RoundToStrideScenario] = {
    "already_rounded": RoundToStrideScenario(64, 64, 64),
    "just_above_stride": RoundToStrideScenario(65, 64, 64),
    "halfway": RoundToStrideScenario(96, 64, 128),
    "double_stride": RoundToStrideScenario(128, 64, 128),
    "large_aligned": RoundToStrideScenario(1024, 64, 1024),
    "large_unaligned": RoundToStrideScenario(1000, 64, 1024),
    "smaller_stride": RoundToStrideScenario(100, 32, 96),
    "zero": RoundToStrideScenario(0, 64, 0),
}


class DefaultStrideScenario(typing.NamedTuple):
    """An input and expected result when using the default stride."""

    value: int
    expected: int


DEFAULT_STRIDE_SCENARIOS: dict[str, DefaultStrideScenario] = {
    "aligned": DefaultStrideScenario(64, 64),
    "halfway": DefaultStrideScenario(96, 128),
    "below_half": DefaultStrideScenario(32, 0),
    "above_half": DefaultStrideScenario(33, 64),
}


class TestRoundToStride:
    """Test the round_to_stride utility function."""

    @pytest.mark.parametrize("scenario", ROUND_TO_STRIDE_SCENARIOS.values(), ids=ROUND_TO_STRIDE_SCENARIOS.keys())
    def test_round_to_stride(self, scenario: RoundToStrideScenario) -> None:
        """Test that round_to_stride rounds to the nearest multiple of stride."""
        assert round_to_stride(scenario.value, scenario.stride) == scenario.expected

    @pytest.mark.parametrize("scenario", DEFAULT_STRIDE_SCENARIOS.values(), ids=DEFAULT_STRIDE_SCENARIOS.keys())
    def test_round_to_stride_default(self, scenario: DefaultStrideScenario) -> None:
        """Test that round_to_stride uses default stride of 64."""
        assert round_to_stride(scenario.value) == scenario.expected


MANGA_OCR_ERROR = ModelLoadError(name=ModelName.manga_ocr, error=RuntimeError("model broken"))


class StatusScenario(typing.NamedTuple):
    """A test scenario for ModelLoaderStatus properties."""

    status: ModelLoaderStatus
    all_ready: bool
    any_loading: bool
    all_settled: bool


STATUS_SCENARIOS: dict[str, StatusScenario] = {
    "all_loaded": StatusScenario(
        status=ModelLoaderStatus(total_count=2, ready_count=2, errors=[]),
        all_ready=True,
        any_loading=False,
        all_settled=True,
    ),
    "partially_loaded": StatusScenario(
        status=ModelLoaderStatus(total_count=2, ready_count=1, errors=[]),
        all_ready=False,
        any_loading=True,
        all_settled=False,
    ),
    "none_loaded": StatusScenario(
        status=ModelLoaderStatus(total_count=2, ready_count=0, errors=[]),
        all_ready=False,
        any_loading=True,
        all_settled=False,
    ),
    "settled_with_error": StatusScenario(
        status=ModelLoaderStatus(total_count=2, ready_count=1, errors=[MANGA_OCR_ERROR]),
        all_ready=False,
        any_loading=False,
        all_settled=True,
    ),
    "all_failed": StatusScenario(
        status=ModelLoaderStatus(total_count=1, ready_count=0, errors=[MANGA_OCR_ERROR]),
        all_ready=False,
        any_loading=False,
        all_settled=True,
    ),
}


class StatusMessageScenario(typing.NamedTuple):
    """Model counts, optional failure, and expected status text."""

    total_count: int
    ready_count: int
    has_error: bool
    expected_substring: str


STATUS_MESSAGE_SCENARIOS: dict[str, StatusMessageScenario] = {
    "ready": StatusMessageScenario(2, 2, False, "OCR ready."),
    "loading": StatusMessageScenario(2, 0, False, "Models are loading..."),
    "failed": StatusMessageScenario(2, 1, True, "manga_ocr"),
}


class TestModelLoaderStatus:
    """Test the ModelLoaderStatus named tuple properties."""

    @pytest.mark.parametrize("scenario", STATUS_SCENARIOS.values(), ids=STATUS_SCENARIOS.keys())
    def test_all_ready(self, scenario: StatusScenario) -> None:
        """Test all_ready property for various scenarios."""
        assert scenario.status.all_ready is scenario.all_ready
        assert scenario.status.any_loading is scenario.any_loading
        assert scenario.status.all_settled is scenario.all_settled

    @pytest.mark.parametrize("scenario", STATUS_MESSAGE_SCENARIOS.values(), ids=STATUS_MESSAGE_SCENARIOS.keys())
    def test_what(self, scenario: StatusMessageScenario) -> None:
        """Test what() returns appropriate status messages."""
        errors = (
            (ModelLoadError(name=ModelName.manga_ocr, error=RuntimeError("model broken")),)
            if scenario.has_error
            else ()
        )
        status = ModelLoaderStatus(scenario.total_count, scenario.ready_count, errors)
        assert scenario.expected_substring in status.what()


class ClassNameSubject:
    """A nested class used to verify class_name's plain-class behavior."""

    pass


class ClassNameDerived(ClassNameSubject):
    """A subclass used to verify class_name reports the runtime class, not the base class."""

    pass


class ClassNameScenario(typing.NamedTuple):
    """A scenario describing an object/instance and the expected class_name() output."""

    obj: object
    expected: str


CLASS_NAME_SCENARIOS: dict[str, ClassNameScenario] = {
    "builtin_int": ClassNameScenario(obj=42, expected="int"),
    "builtin_str": ClassNameScenario(obj="hello", expected="str"),
    "builtin_list": ClassNameScenario(obj=[1, 2, 3], expected="list"),
    "custom_class_instance": ClassNameScenario(obj=ClassNameSubject(), expected="ClassNameSubject"),
    "subclass_reports_runtime_class": ClassNameScenario(obj=ClassNameDerived(), expected="ClassNameDerived"),
    "exception_instance": ClassNameScenario(obj=RuntimeError("oops"), expected="RuntimeError"),
}


class TestClassName:
    """class_name returns the runtime class name of any object."""

    @pytest.mark.parametrize("scenario", CLASS_NAME_SCENARIOS.values(), ids=CLASS_NAME_SCENARIOS.keys())
    def test_class_name(self, scenario: ClassNameScenario) -> None:
        """Each scenario asserts the function returns the expected class name."""
        assert class_name(scenario.obj) == scenario.expected


def make_red_image(size: tuple[int, int] = (4, 4)) -> Image.Image:
    """Build a small in-memory red RGB image to act as a stand-in for a speech-bubble crop."""
    return Image.new("RGB", size, color=(255, 0, 0))


def make_bubble_block(
    *,
    line_count: int = 0,
    chunks_per_line: int = 1,
) -> SpeechBubbleBlock:
    """Build a SpeechBubbleBlock with line_count lines, each holding chunks_per_line images."""
    block = SpeechBubbleBlock(
        box=Rect(0, 0, 4, 4),
        box_image=make_red_image(),
        vertical=False,
        font_size=12.0,
    )
    for _line_idx in range(line_count):
        block.lines.append([make_red_image() for _chunk_idx in range(chunks_per_line)])
    return block


class SaveBubbleScenario(typing.NamedTuple):
    """A scenario describing a sequence of SpeechBubbleBlocks and the expected output filenames."""

    blocks: list[SpeechBubbleBlock]
    expected_filenames: list[str]


SAVE_BUBBLE_SCENARIOS: dict[str, SaveBubbleScenario] = {
    "single_block_no_lines": SaveBubbleScenario(
        blocks=[make_bubble_block()],
        expected_filenames=["block_0_box.png"],
    ),
    "single_block_two_lines_one_chunk_each": SaveBubbleScenario(
        blocks=[make_bubble_block(line_count=2, chunks_per_line=1)],
        expected_filenames=[
            "block_0_box.png",
            "block_0_line_0_chunk_0.png",
            "block_0_line_1_chunk_0.png",
        ],
    ),
    "two_blocks_one_with_chunks": SaveBubbleScenario(
        blocks=[make_bubble_block(), make_bubble_block(line_count=1, chunks_per_line=2)],
        expected_filenames=[
            "block_0_box.png",
            "block_1_box.png",
            "block_1_line_0_chunk_0.png",
            "block_1_line_0_chunk_1.png",
        ],
    ),
}


class TestSaveBubbleImages:
    """save_bubble_images writes the box image plus each chunk to the output directory."""

    @pytest.mark.parametrize("scenario", SAVE_BUBBLE_SCENARIOS.values(), ids=SAVE_BUBBLE_SCENARIOS.keys())
    def test_returned_paths_exist(self, scenario: SaveBubbleScenario, tmp_path: pathlib.Path) -> None:
        """Every path returned by save_bubble_images points to an existing file on disk."""
        saved = save_bubble_images(scenario.blocks, output_dir=tmp_path / "out")
        assert all(path.is_file() for path in saved)

    @pytest.mark.parametrize("scenario", SAVE_BUBBLE_SCENARIOS.values(), ids=SAVE_BUBBLE_SCENARIOS.keys())
    def test_filenames_match_pattern(self, scenario: SaveBubbleScenario, tmp_path: pathlib.Path) -> None:
        """The basenames of saved files match the expected pattern for box/line/chunk indices."""
        saved = save_bubble_images(scenario.blocks, output_dir=tmp_path / "out")
        assert sorted(p.name for p in saved) == sorted(scenario.expected_filenames)

    def test_creates_nested_output_directory(self, tmp_path: pathlib.Path) -> None:
        """save_bubble_images creates the output directory (and parents) if it does not exist."""
        nested = tmp_path / "a/b/c"
        save_bubble_images([make_bubble_block()], output_dir=nested)
        assert nested.is_dir()


class DeduplicateScenario(typing.NamedTuple):
    """Input values and their expected consecutive-deduplicated output."""

    items: Sequence[str | int]
    expected: Sequence[str | int]


DEDUPLICATE_SCENARIOS: dict[str, DeduplicateScenario] = {
    "empty": DeduplicateScenario((), ()),
    "single": DeduplicateScenario(("A",), ("A",)),
    "repeated": DeduplicateScenario(("A", "A", "A"), ("A",)),
    "nonconsecutive_repeat": DeduplicateScenario(("A", "A", "B", "A"), ("A", "B", "A")),
    "distinct": DeduplicateScenario(("A", "B", "C"), ("A", "B", "C")),
    "empty_string": DeduplicateScenario(("", "", "A"), ("", "A")),
    "middle_empty_string": DeduplicateScenario(("A", "", "", "B"), ("A", "", "B")),
    "numbers": DeduplicateScenario((1, 1, 2, 2, 1), (1, 2, 1)),
}


class TestDeduplicate:
    """deduplicate drops consecutive duplicates while preserving order."""

    @pytest.mark.parametrize("scenario", DEDUPLICATE_SCENARIOS.values(), ids=DEDUPLICATE_SCENARIOS.keys())
    def test_deduplicate(self, scenario: DeduplicateScenario) -> None:
        """Consecutive duplicate values collapse without changing later repetitions."""
        assert list(deduplicate(scenario.items)) == list(scenario.expected)
