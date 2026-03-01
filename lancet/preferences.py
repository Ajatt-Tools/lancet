# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
import dataclasses
import sys
from types import SimpleNamespace

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QSpinBox,
    QVBoxLayout,
    QWidget,
    QApplication,
    QAbstractButton,
    QLayout,
    QGridLayout,
)
from loguru import logger

from lancet.config import Config
from lancet.consts import APP_NAME, APP_LOGO_PATH, GEOMETRY_FILE_PATH
from lancet.gui.enum_select_combo import EnumSelectCombo
from lancet.gui.grab_key import ShortCutGrabButton
from lancet.gui.ocr_history_widget import OcrHistoryWidget
from lancet.gui.ocr_model_list import ModelListEditor
from lancet.ocr_history import OcrHistory


@dataclasses.dataclass(frozen=True)
class SettingsApplyResult:
    """Holds the outcome of applying settings: success flag and optional error."""

    success: bool = False
    error: Exception | None = None


def ui_translate(key: str) -> str:
    """Convert a snake_case config key to a human-readable label."""
    return key.capitalize().replace("_", " ")


class SecondsSpinBox(QSpinBox):
    """A spin box pre-configured for selecting a duration in seconds."""

    min: int = 1
    max: int = 120
    suffix: str = "seconds"

    def __init__(self, initial_value: int, parent: QWidget | None = None) -> None:
        """Initialize the spin box with range, suffix, and initial value."""
        super().__init__(parent)
        self.setRange(self.min, self.max)
        self.setSuffix(f" {self.suffix}")
        self.setValue(initial_value)


class HistorySizeSpinBox(SecondsSpinBox):
    min: int = 1
    max: int = 1_000
    suffix: str = "items"


class FormWidgets(SimpleNamespace):
    """Container holding all form widgets used in the preferences dialog."""

    copy_to: EnumSelectCombo
    notification_duration: SecondsSpinBox
    huggingface_model: ModelListEditor
    force_cpu: QCheckBox
    ocr_shortcut: ShortCutGrabButton
    screenshot_shortcut: ShortCutGrabButton
    max_history_size: HistorySizeSpinBox


class PreferencesDialog(QDialog):
    """Preferences dialog for editing all Config fields, with an OCR history panel on the right."""

    settings_applied = pyqtSignal(SettingsApplyResult)

    def __init__(self, cfg: Config, history: OcrHistory, parent: QWidget | None = None) -> None:
        """Initialize the dialog, creating form widgets for each config field and the history panel."""
        super().__init__(parent)
        self._cfg = cfg
        self._history = history
        self.history_list = OcrHistoryWidget(history.entries())

        self.setWindowIcon(QIcon(str(APP_LOGO_PATH)))
        self.setWindowTitle(f"{APP_NAME} Preferences")
        self.setMinimumWidth(700)

        # Two-column layout: settings on the left, history on the right
        columns_layout = QGridLayout()
        self.setLayout(columns_layout)

        # Left column: settings
        left_column = QVBoxLayout()
        columns_layout.addLayout(left_column, 1, 1)

        self._widgets = FormWidgets()

        # OCR destination
        self._widgets.copy_to = EnumSelectCombo(initial_value=cfg.copy_to)

        # Notification duration
        self._widgets.notification_duration = SecondsSpinBox(initial_value=cfg.notification_duration_sec)

        # Huggingface model name
        self._widgets.huggingface_model = ModelListEditor()
        self._widgets.huggingface_model.set_items(cfg.huggingface_models)
        self._widgets.huggingface_model.set_current(cfg.huggingface_model_name)

        # Force CPU
        self._widgets.force_cpu = QCheckBox()
        self._widgets.force_cpu.setChecked(cfg.force_cpu)

        # OCR shortcut
        self._widgets.ocr_shortcut = ShortCutGrabButton(initial_value=cfg.ocr_shortcut)

        # Screenshot shortcut
        self._widgets.screenshot_shortcut = ShortCutGrabButton(initial_value=cfg.screenshot_shortcut)

        # Max history size
        self._widgets.max_history_size = HistorySizeSpinBox(initial_value=cfg.max_history_size)

        left_column.addLayout(self._make_settings_layout())

        # Right column: OCR history
        columns_layout.addWidget(self.history_list, 1, 2)

        # Dialog buttons
        self._button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Apply
            | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.RestoreDefaults
        )
        self._button_box.clicked.connect(self._on_button_clicked)
        columns_layout.addWidget(self._button_box, 3, 1, 1, 2)  # row, col, rowspan, colspan

        # Restore geometry
        self._restore_geometry()

    def _make_settings_layout(self) -> QLayout:
        """Build a form layout with labeled rows for each settings widget."""
        layout = QFormLayout()
        for key, widget in self._widgets.__dict__.items():
            layout.addRow(ui_translate(key), widget)
        return layout

    def _save_geometry(self) -> None:
        """Save the dialog's position and size to QSettings."""
        try:
            GEOMETRY_FILE_PATH.parent.mkdir(exist_ok=True, parents=True)
            GEOMETRY_FILE_PATH.write_bytes(self.saveGeometry())
        except OSError as e:
            logger.error(f"can't save geometry: {e}")

    def _restore_geometry(self) -> None:
        """Restore the dialog's position and size from QSettings."""
        try:
            geometry = GEOMETRY_FILE_PATH.read_bytes()
        except OSError:
            return
        else:
            if geometry:
                self.restoreGeometry(geometry)

    def reject(self) -> None:
        """Save geometry and reject the dialog."""
        self._save_geometry()
        return super().reject()

    def accept(self) -> None:
        """Save geometry and accept the dialog."""
        self._save_geometry()
        return super().accept()

    def _on_button_clicked(self, button: QAbstractButton) -> None:
        """Route button clicks to the appropriate action based on the button's role."""
        match self._button_box.buttonRole(button):
            case QDialogButtonBox.ButtonRole.ApplyRole:
                self._apply()
            case QDialogButtonBox.ButtonRole.RejectRole:
                self.reject()
            case QDialogButtonBox.ButtonRole.ResetRole:
                self._restore_defaults()

    def _apply(self) -> None:
        """Write current widget values back to the config and save to disk."""
        self._cfg.copy_to = self._widgets.copy_to.currentData()
        self._cfg.notification_duration_sec = self._widgets.notification_duration.value()
        self._cfg.max_history_size = self._widgets.max_history_size.value()
        self._cfg.huggingface_model_name = self._widgets.huggingface_model.current_text()
        self._cfg.huggingface_models = self._widgets.huggingface_model.models_as_list()
        self._cfg.force_cpu = self._widgets.force_cpu.isChecked()
        self._cfg.ocr_shortcut = self._widgets.ocr_shortcut.current_shortcut()
        self._cfg.screenshot_shortcut = self._widgets.screenshot_shortcut.current_shortcut()
        try:
            self._cfg.save_to_file()
        except Exception as e:
            self.settings_applied.emit(SettingsApplyResult(error=e))
        else:
            self.settings_applied.emit(SettingsApplyResult(success=True))
        self._history.set_entries(self.history_list.as_list())
        self.accept()

    def _restore_defaults(self) -> None:
        """Reset all form widgets to the default config values."""
        defaults = Config()
        self._widgets.copy_to.set_current(defaults.copy_to)
        self._widgets.notification_duration.setValue(defaults.notification_duration_sec)
        self._widgets.max_history_size.setValue(defaults.max_history_size)
        self._widgets.huggingface_model.set_current(defaults.huggingface_model_name)
        self._widgets.huggingface_model.set_items(defaults.huggingface_models)
        self._widgets.force_cpu.setChecked(defaults.force_cpu)
        self._widgets.ocr_shortcut.set_keyboard_shortcut(defaults.ocr_shortcut)
        self._widgets.screenshot_shortcut.set_keyboard_shortcut(defaults.screenshot_shortcut)


def playground() -> None:
    """Launch the preferences dialog standalone for testing."""
    app = QApplication(sys.argv)
    cfg = Config.read_from_file()
    history = OcrHistory(cfg)
    form = PreferencesDialog(cfg, history)
    form.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    playground()
