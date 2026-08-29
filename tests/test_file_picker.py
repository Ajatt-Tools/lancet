# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import pathlib
import typing
from collections.abc import Sequence
from unittest.mock import Mock

import pytest
from PyQt6.QtWidgets import QApplication, QFileDialog

from lancet.gui.file_picker import LancetFilePicker, best_bin_directory


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
    """Test best_bin_directory with mocked default hardcoded paths."""

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
            "lancet.gui.file_picker.default_hardcoded_paths",
            lambda: candidate_dirs,
        )

        result = best_bin_directory()
        if scenario.expected_index is None:
            assert result == str(pathlib.Path.home())
        else:
            assert result == str(candidate_dirs[scenario.expected_index])


class FilePickerScenario(typing.NamedTuple):
    """A file dialog result and the expected value retained by LancetFilePicker."""

    initial_path: str
    selected_path: str
    expected_path: str


FILE_PICKER_SCENARIOS: dict[str, FilePickerScenario] = {
    "accepted_selection_replaces_path": FilePickerScenario(
        initial_path=" /usr/bin/firefox ",
        selected_path="/opt/librewolf/librewolf",
        expected_path="/opt/librewolf/librewolf",
    ),
    "canceled_selection_keeps_path": FilePickerScenario(
        initial_path=" /usr/bin/firefox ",
        selected_path="",
        expected_path="/usr/bin/firefox",
    ),
}


class TestLancetFilePicker:
    """Test LancetFilePicker path normalization and file dialog behavior."""

    @pytest.mark.parametrize("scenario", FILE_PICKER_SCENARIOS.values(), ids=FILE_PICKER_SCENARIOS.keys())
    def test_browse(self, scenario: FilePickerScenario, monkeypatch: pytest.MonkeyPatch, qapp: QApplication) -> None:
        """Browse updates the path only after selection and preserves configured dialog details."""
        picker = LancetFilePicker()
        picker.set_file_path(scenario.initial_path)
        picker.set_dialog_title("Select browser")
        picker.set_dialog_filter("Executables (*)")
        dialog = Mock(return_value=(scenario.selected_path, "Executables (*)"))
        monkeypatch.setattr(QFileDialog, "getOpenFileName", dialog)

        picker._on_browse()

        assert picker.get_file_path() == scenario.expected_path
        assert dialog.call_args.kwargs == {
            "parent": picker,
            "caption": "Select browser",
            "directory": "/usr/bin/firefox",
            "filter": "Executables (*)",
        }
