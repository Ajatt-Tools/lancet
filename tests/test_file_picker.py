# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import pathlib
import typing
from collections.abc import Sequence

import pytest

from lancet.gui.file_picker import best_bin_directory


class BestBinDirScenario(typing.NamedTuple):
    """A scenario for best_bin_directory with mock bin directories."""

    existing_dirs: Sequence[int]  # indices of the candidate dirs that exist on the fake filesystem
    expected_index: int | None  # index of the expected result dir; None means the user's home directory


BEST_BIN_DIR_SCENARIOS: dict[str, BestBinDirScenario] = {
    "first_dir_exists": BestBinDirScenario(
        existing_dirs=(0,),
        expected_index=0,
    ),
    "later_dir_exists": BestBinDirScenario(
        existing_dirs=(1,),
        expected_index=1,
    ),
    "first_dir_wins": BestBinDirScenario(
        existing_dirs=(0, 2),
        expected_index=0,
    ),
    "no_dirs_fall_back_to_home": BestBinDirScenario(
        existing_dirs=(),
        expected_index=None,
    ),
}


class TestBestBinDirectory:
    """Test best_bin_directory with mocked HARDCODED_PATHS."""

    @pytest.mark.parametrize("scenario", BEST_BIN_DIR_SCENARIOS.values(), ids=BEST_BIN_DIR_SCENARIOS.keys())
    def test_resolve(
        self,
        scenario: BestBinDirScenario,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: pathlib.Path,
    ) -> None:
        """best_bin_directory returns the first existing dir, or home when none exist."""
        candidate_dirs = (tmp_path / "bin1", tmp_path / "bin2", tmp_path / "bin3")
        for index in scenario.existing_dirs:
            candidate_dirs[index].mkdir(parents=True)

        monkeypatch.setattr(
            "lancet.gui.file_picker.HARDCODED_PATHS",
            tuple(candidate_dirs),
        )

        result = best_bin_directory()
        if scenario.expected_index is None:
            assert result == str(pathlib.Path.home())
        else:
            assert result == str(candidate_dirs[scenario.expected_index])
