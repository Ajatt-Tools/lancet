# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import pathlib
import typing
from collections.abc import Sequence
from unittest.mock import Mock, call, patch

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from lancet.config import Config
from lancet.gui.geom_dialog import SaveAndRestoreGeomDialog
from lancet.gui.ocr_history_widget import OcrHistoryWidget
from lancet.gui.preferences import (
    PreferencesDialog,
    PreferencesDialogSplitter,
    SettingsApplyResult,
)
from lancet.gui.preferences_widget import MainPreferencesWidget
from lancet.ocr_history import OcrHistory

STATE_FILE_NAME: typing.Final[str] = "geometry.preferences.splitter"


class SplitterParts(typing.NamedTuple):
    """A configured splitter and its panes."""

    splitter: PreferencesDialogSplitter
    tabs: MainPreferencesWidget
    history: OcrHistoryWidget


def make_splitter(state_file: pathlib.Path) -> SplitterParts:
    """Create a splitter with independent production pane instances."""
    tabs = MainPreferencesWidget(Config())
    history = OcrHistoryWidget([])
    splitter = PreferencesDialogSplitter()
    splitter._splitter_state_file = state_file
    splitter.resize(900, 500)
    splitter.create_layout(tabs, history)
    return SplitterParts(splitter, tabs, history)


def patch_state_file(monkeypatch: pytest.MonkeyPatch, state_file: pathlib.Path) -> None:
    """Redirect the splitter's state file to a temporary location."""
    monkeypatch.setattr(PreferencesDialogSplitter, "_splitter_state_file", state_file)


def patch_dialog_files(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    """Redirect dialog geometry and splitter persistence files to tmp_path."""
    monkeypatch.setattr(PreferencesDialog, "_geom_file", tmp_path / "geometry.preferences")
    patch_state_file(monkeypatch, tmp_path / STATE_FILE_NAME)


def make_preferences_dialog(cfg: Config) -> PreferencesDialog:
    """Create a PreferencesDialog with an empty OCR history."""
    return PreferencesDialog(cfg, OcrHistory(cfg.max_history_size))


class SplitterLayoutScenario(typing.NamedTuple):
    """Expected splitter pane arrangement."""

    orientation: Qt.Orientation
    collapsible: bool
    pane_count: int


SPLITTER_LAYOUT_SCENARIOS: dict[str, SplitterLayoutScenario] = {
    "horizontal_two_pane_layout": SplitterLayoutScenario(Qt.Orientation.Horizontal, False, 2)
}


class TestSplitterLayout:
    """Test splitter pane configuration with production pane instances."""

    @pytest.mark.parametrize("scenario", SPLITTER_LAYOUT_SCENARIOS.values(), ids=SPLITTER_LAYOUT_SCENARIOS.keys())
    def test_layout(self, scenario: SplitterLayoutScenario, qapp: QApplication, tmp_path: pathlib.Path) -> None:
        """The splitter contains two ordered, non-collapsible horizontal panes."""
        parts = make_splitter(tmp_path / "splitter.state")
        assert parts.splitter.orientation() == scenario.orientation
        assert parts.splitter.childrenCollapsible() == scenario.collapsible
        assert parts.splitter.count() == scenario.pane_count
        assert parts.splitter.widget(0) is parts.tabs
        assert parts.splitter.widget(1) is parts.history


class SplitterPersistenceScenario(typing.NamedTuple):
    """Requested splitter sizes to persist."""

    requested_sizes: Sequence[int]


SPLITTER_PERSISTENCE_SCENARIOS: dict[str, SplitterPersistenceScenario] = {
    "settings_narrower": SplitterPersistenceScenario((240, 660)),
    "settings_wider": SplitterPersistenceScenario((560, 340)),
}


class TestSplitterPersistence:
    """Test splitter state round trips with production panes."""

    @pytest.mark.parametrize(
        "scenario", SPLITTER_PERSISTENCE_SCENARIOS.values(), ids=SPLITTER_PERSISTENCE_SCENARIOS.keys()
    )
    def test_round_trip(
        self, scenario: SplitterPersistenceScenario, qapp: QApplication, tmp_path: pathlib.Path
    ) -> None:
        """A saved splitter position is restored into an equivalent splitter."""
        state_file = tmp_path / "splitter.state"
        writer = make_splitter(state_file)
        writer.splitter.setSizes(list(scenario.requested_sizes))
        qapp.processEvents()
        expected_sizes = writer.splitter.sizes()
        assert writer.splitter.write_splitter_state() is writer.splitter

        reader = make_splitter(state_file)
        assert reader.splitter.restore_splitter_state() is reader.splitter
        assert reader.splitter.sizes() == expected_sizes

    @pytest.mark.parametrize(
        "scenario", SPLITTER_PERSISTENCE_SCENARIOS.values(), ids=SPLITTER_PERSISTENCE_SCENARIOS.keys()
    )
    def test_restore_without_state_file_is_noop(
        self, scenario: SplitterPersistenceScenario, qapp: QApplication, tmp_path: pathlib.Path
    ) -> None:
        """With no state file, restore leaves production pane sizes untouched."""
        parts = make_splitter(tmp_path / "missing.state")
        parts.splitter.setSizes(list(scenario.requested_sizes))
        qapp.processEvents()
        sizes_before = parts.splitter.sizes()
        assert parts.splitter.restore_splitter_state() is parts.splitter
        assert parts.splitter.sizes() == sizes_before


class SplitterReadScenario(typing.NamedTuple):
    """A state-file condition and expected bytes."""

    contents: bytes | None
    expected: bytes | None
    expected_warning_count: int


SPLITTER_READ_SCENARIOS: dict[str, SplitterReadScenario] = {
    "missing": SplitterReadScenario(None, None, 0),
    "empty": SplitterReadScenario(b"", None, 0),
    "nonempty": SplitterReadScenario(b"opaque-qt-state", b"opaque-qt-state", 0),
}


class TestSplitterRead:
    """Test recoverable splitter state-file conditions with production panes."""

    @pytest.mark.parametrize("scenario", SPLITTER_READ_SCENARIOS.values(), ids=SPLITTER_READ_SCENARIOS.keys())
    def test_read(
        self,
        scenario: SplitterReadScenario,
        qapp: QApplication,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Missing and empty files return None; nonempty bytes are returned unchanged."""
        state_file = tmp_path / "splitter.state"
        if scenario.contents is not None:
            state_file.write_bytes(scenario.contents)
        warning = Mock()
        monkeypatch.setattr("lancet.gui.preferences.logger.warning", warning)
        assert make_splitter(state_file).splitter.read_splitter_state() == scenario.expected
        assert warning.call_count == scenario.expected_warning_count


class SplitterIoErrorScenario(typing.NamedTuple):
    """A failing splitter-state operation and expected log method."""

    operation: typing.Literal["read", "write"]
    error: OSError
    logger_method: typing.Literal["warning", "error"]


SPLITTER_IO_ERROR_SCENARIOS: dict[str, SplitterIoErrorScenario] = {
    "read_permission_denied": SplitterIoErrorScenario("read", PermissionError("denied"), "warning"),
    "write_permission_denied": SplitterIoErrorScenario("write", PermissionError("denied"), "error"),
}


class TestSplitterIoErrors:
    """Test that splitter-state I/O errors are logged and swallowed."""

    @pytest.mark.parametrize("scenario", SPLITTER_IO_ERROR_SCENARIOS.values(), ids=SPLITTER_IO_ERROR_SCENARIOS.keys())
    def test_error(
        self,
        scenario: SplitterIoErrorScenario,
        qapp: QApplication,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Read and write failures return safely and log the appropriate message."""
        splitter = make_splitter(tmp_path / "splitter.state").splitter
        logger = Mock()
        monkeypatch.setattr("lancet.gui.preferences.logger", logger)
        path_method = "read_bytes" if scenario.operation == "read" else "write_bytes"
        monkeypatch.setattr(pathlib.Path, path_method, Mock(side_effect=scenario.error))

        if scenario.operation == "read":
            assert splitter.read_splitter_state() is None
            expected_message = f"can't read splitter state: {scenario.error}"
        else:
            assert splitter.write_splitter_state() is splitter
            expected_message = f"can't save splitter state: {scenario.error}"
        assert getattr(logger, scenario.logger_method).call_args == call(expected_message)


SAVE_GEOMETRY_SCENARIOS: dict[str, int] = {"save_dialog_and_splitter": 1}


class TestPreferencesDialogGeometry:
    """Test mocked integration between dialog and splitter persistence."""

    @pytest.mark.parametrize("expected_calls", SAVE_GEOMETRY_SCENARIOS.values(), ids=SAVE_GEOMETRY_SCENARIOS.keys())
    def test_save_geometry(self, expected_calls: int, qapp: QApplication) -> None:
        """Saving dialog geometry also writes the splitter state exactly once."""
        with patch.object(PreferencesDialogSplitter, "restore_splitter_state", autospec=True):
            dialog = PreferencesDialog(Config(), OcrHistory(100))
        with (
            patch.object(SaveAndRestoreGeomDialog, "_save_geometry", autospec=True) as save_dialog,
            patch.object(PreferencesDialogSplitter, "write_splitter_state", autospec=True) as save_splitter,
        ):
            dialog._save_geometry()
        assert save_dialog.call_count == expected_calls
        assert save_splitter.call_count == expected_calls


class WriteScenario(typing.NamedTuple):
    """A writable or missing-parent state-file target."""

    in_missing_dir: bool
    file_expected: bool


WRITE_SCENARIOS: dict[str, WriteScenario] = {
    "writes_state_bytes": WriteScenario(in_missing_dir=False, file_expected=True),
    "missing_parent_dir_is_swallowed": WriteScenario(in_missing_dir=True, file_expected=False),
}


class TestWriteSplitterState:
    """Test real state writes and missing-parent failures."""

    @pytest.mark.parametrize("scenario", WRITE_SCENARIOS.values(), ids=WRITE_SCENARIOS.keys())
    def test_write(
        self,
        scenario: WriteScenario,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: pathlib.Path,
        qapp: QApplication,
    ) -> None:
        """A writable target receives state bytes; an unwritable target is skipped."""
        state_file = tmp_path / STATE_FILE_NAME
        if scenario.in_missing_dir:
            state_file = tmp_path / "nonexistent-dir" / STATE_FILE_NAME
        patch_state_file(monkeypatch, state_file)
        splitter = PreferencesDialogSplitter()

        splitter.write_splitter_state()

        if scenario.file_expected:
            assert state_file.read_bytes() == splitter.saveState()
        else:
            assert state_file.exists() is False


class TestPreferencesDialogLifecycle:
    """Test Apply, Restore Defaults, and real persistence wiring."""

    def test_restore_defaults(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: pathlib.Path,
        qapp: QApplication,
    ) -> None:
        """Restore Defaults replaces current widget values with a fresh default Config."""
        patch_dialog_files(monkeypatch, tmp_path)
        dialog = make_preferences_dialog(Config(force_cpu=True))

        dialog._restore_defaults()

        assert dialog._tabs.widgets.force_cpu.isChecked() is False

    @pytest.mark.parametrize(
        "save_error,expected_success",
        [(None, True), (OSError("disk full"), False)],
        ids=["apply_succeeds", "save_failure_emits_error"],
    )
    def test_apply(
        self,
        save_error: OSError | None,
        expected_success: bool,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: pathlib.Path,
        qapp: QApplication,
    ) -> None:
        """Apply copies values and emits a result according to config persistence."""
        patch_dialog_files(monkeypatch, tmp_path)
        cfg = Config()
        save = Mock(side_effect=save_error)
        monkeypatch.setattr(cfg, "save_to_file", save)
        dialog = make_preferences_dialog(cfg)
        results: list[SettingsApplyResult] = []
        dialog.settings_applied.connect(results.append)
        dialog._tabs.widgets.force_cpu.setChecked(True)

        dialog._apply()

        assert cfg.force_cpu is True
        assert results[0].success is expected_success
        assert (results[0].error is None) is expected_success

    def test_save_geometry_persists_splitter(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: pathlib.Path,
        qapp: QApplication,
    ) -> None:
        """Saving dialog geometry creates both geometry and splitter state files."""
        patch_dialog_files(monkeypatch, tmp_path)
        dialog = make_preferences_dialog(Config())

        dialog._save_geometry()

        assert (tmp_path / "geometry.preferences").is_file()
        assert (tmp_path / STATE_FILE_NAME).is_file()
