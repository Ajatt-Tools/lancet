# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
import dataclasses
import pathlib
import sys
import typing

from loguru import logger
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QDialogButtonBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)
from zala.utils import qconnect

from lancet.config import Config
from lancet.consts import (
    APP_LOGO_PATH,
    APP_NAME,
    GEOMETRY_FILE_PATH,
    PREFERENCES_SPLITTER_HISTORY_WIDTH,
    PREFERENCES_SPLITTER_SETTINGS_WIDTH,
)
from lancet.gui.geom_dialog import SaveAndRestoreGeomDialog
from lancet.gui.ocr_history_widget import OcrHistoryWidget
from lancet.gui.preferences_widget import MainPreferencesWidget
from lancet.ocr_history import OcrHistory


@dataclasses.dataclass(frozen=True)
class SettingsApplyResult:
    """Holds the outcome of applying settings: success flag and optional error."""

    success: bool = False
    error: Exception | None = None
    ocr_history: list[str] = dataclasses.field(default_factory=list)


class PreferencesDialogSplitter(QSplitter):
    """Horizontal splitter separating the settings and OCR history panes, with persistent position."""

    _splitter_state_file: pathlib.Path = GEOMETRY_FILE_PATH.with_suffix(".preferences.splitter")

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the splitter in horizontal orientation."""
        super().__init__(parent)
        self.setOrientation(Qt.Orientation.Horizontal)

    def create_layout(self, tabs: MainPreferencesWidget, history_list: OcrHistoryWidget) -> typing.Self:
        """Add the settings and history panes, configure resize behavior, and return self."""
        # Two panes separated by a draggable splitter: settings on the left, history on the right.
        self.addWidget(tabs)
        self.addWidget(history_list)
        self.setChildrenCollapsible(False)
        # The settings pane keeps its width; the history pane absorbs extra space on resize.
        self.setStretchFactor(0, 0)
        self.setStretchFactor(1, 1)
        self.setSizes([PREFERENCES_SPLITTER_SETTINGS_WIDTH, PREFERENCES_SPLITTER_HISTORY_WIDTH])
        return self

    def read_splitter_state(self) -> bytes | None:
        """Return the saved splitter state bytes, or None if missing or empty."""
        try:
            state = self._splitter_state_file.read_bytes()
        except OSError as e:
            logger.warning(f"can't read splitter state: {e}")
            return None
        return state or None

    def write_splitter_state(self) -> typing.Self:
        """Write splitter state bytes to disk, logging instead of raising on failure."""
        try:
            self._splitter_state_file.write_bytes(self.saveState().data())
        except OSError as e:
            logger.error(f"can't save splitter state: {e}")
        return self

    def restore_splitter_state(self) -> typing.Self:
        """Restore the splitter position from the previous session, if saved."""
        if state := self.read_splitter_state():
            self.restoreState(state)
        return self


class PreferencesDialog(SaveAndRestoreGeomDialog):
    """Preferences dialog for editing all Config fields, with an OCR history panel on the right."""

    _name: str = "preferences"
    _geom_file: pathlib.Path = GEOMETRY_FILE_PATH.with_suffix(".preferences")
    settings_applied = pyqtSignal(SettingsApplyResult)

    def __init__(self, cfg: Config, history: OcrHistory, parent: QWidget | None = None) -> None:
        """Initialize the dialog, creating form widgets for each config field and the history panel."""
        super().__init__(parent)
        self._cfg = cfg
        self._history = history
        self._tabs = MainPreferencesWidget(self._cfg)
        self.history_list = OcrHistoryWidget(history.entries())

        self.setWindowIcon(QIcon(str(APP_LOGO_PATH)))
        self.setWindowTitle(f"{APP_NAME} {self.name.capitalize()}")
        self.setMinimumWidth(700)

        # Dialog buttons
        self._button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Apply
            | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.RestoreDefaults
        )
        # QAbstractButton is passed to the slot.
        # https://doc.qt.io/qt-6/qdialogbuttonbox.html#clicked
        qconnect(self._button_box.clicked, self._on_button_clicked)

        # Two panes separated by a draggable splitter: settings on the left, history on the right.
        self._splitter = PreferencesDialogSplitter().create_layout(self._tabs, self.history_list)

        # Main layout: splitter on top, dialog buttons below.
        self.setLayout(main_layout := QVBoxLayout())
        main_layout.addWidget(self._splitter)
        main_layout.addWidget(self._button_box)

        self._add_tooltips()
        self._splitter.restore_splitter_state()

    def _add_tooltips(self) -> None:
        """Add explanatory tooltips to all preference widgets."""
        self._tabs.add_tooltips()

    def _save_geometry(self) -> None:
        """Save the dialog geometry and the splitter position to disk."""
        super()._save_geometry()
        self._splitter.write_splitter_state()

    def _on_button_clicked(self, button: QAbstractButton) -> None:
        """Route button clicks to the appropriate action based on the button's role."""
        # https://doc.qt.io/qt-6/qdialogbuttonbox.html#clicked
        match self._button_box.buttonRole(button):
            case QDialogButtonBox.ButtonRole.ApplyRole:
                self._apply()
            case QDialogButtonBox.ButtonRole.RejectRole:
                self.reject()
            case QDialogButtonBox.ButtonRole.ResetRole:
                self._restore_defaults()

    def _apply(self) -> None:
        """Write current widget values back to the config and save to disk."""
        self._tabs.copy_settings_to_cfg()

        try:
            self._cfg.save_to_file()
        except Exception as e:
            self.settings_applied.emit(SettingsApplyResult(error=e))
        else:
            self.settings_applied.emit(SettingsApplyResult(success=True, ocr_history=self.history_list.as_list()))
        self.accept()

    def _restore_defaults(self) -> None:
        """Reset all form widgets to the default config values."""
        self._tabs.set_widget_values(values=Config())


def playground() -> None:
    """Launch the preferences dialog standalone for testing."""
    app = QApplication(sys.argv)
    cfg = Config.read_from_file()
    history = OcrHistory(cfg.max_history_size)
    form = PreferencesDialog(cfg, history)
    form.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    playground()
