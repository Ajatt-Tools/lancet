# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
import dataclasses
import pathlib
import sys

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QDialogButtonBox,
    QGridLayout,
    QWidget,
)
from zala.utils import qconnect

from lancet.config import Config
from lancet.consts import APP_LOGO_PATH, APP_NAME, GEOMETRY_FILE_PATH
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

        # Two-column layout: settings on the left, history on the right
        self.setLayout(columns_layout := QGridLayout())
        columns_layout.addWidget(self._tabs, 1, 1)
        columns_layout.addWidget(self.history_list, 1, 2)
        columns_layout.addWidget(self._button_box, 3, 1, 1, 2)  # row, col, rowspan, colspan

        self._add_tooltips()

    def _add_tooltips(self) -> None:
        self._tabs.add_tooltips()

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
