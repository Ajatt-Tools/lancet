# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
import dataclasses
import pathlib
import sys
from types import SimpleNamespace

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialogButtonBox,
    QFormLayout,
    QVBoxLayout,
    QWidget,
    QApplication,
    QAbstractButton,
    QLayout,
    QGridLayout,
)

from lancet.config import Config
from lancet.consts import APP_NAME, APP_LOGO_PATH, GEOMETRY_FILE_PATH
from lancet.gui.color_picker import ColorEditPicker

from lancet.gui.enum_select_combo import EnumSelectCombo
from lancet.gui.geom_dialog import SaveAndRestoreGeomDialog
from lancet.gui.grab_key import ShortCutGrabButton
from lancet.gui.ocr_history_widget import OcrHistoryWidget
from lancet.gui.ocr_model_list import ModelListEditor
from lancet.gui.utils import ui_translate, SecondsSpinBox, HistorySizeSpinBox, BorderThicknessSpinBox
from lancet.ocr_history import OcrHistory


@dataclasses.dataclass(frozen=True)
class SettingsApplyResult:
    """Holds the outcome of applying settings: success flag and optional error."""

    success: bool = False
    error: Exception | None = None
    ocr_history: list[str] = dataclasses.field(default_factory=list)


class FormWidgets(SimpleNamespace):
    """Container holding all form widgets used in the preferences dialog."""

    copy_to: EnumSelectCombo
    notification_duration: SecondsSpinBox
    huggingface_model: ModelListEditor
    force_cpu: QCheckBox
    ocr_shortcut: ShortCutGrabButton
    screenshot_shortcut: ShortCutGrabButton
    max_history_size: HistorySizeSpinBox

    # Screenshot overlay colors
    border_thickness: BorderThicknessSpinBox
    border_color: ColorEditPicker
    fill_color: ColorEditPicker
    outline_color: ColorEditPicker
    fill_brush_color: ColorEditPicker


class PreferencesDialog(SaveAndRestoreGeomDialog):
    """Preferences dialog for editing all Config fields, with an OCR history panel on the right."""

    _geom_file: pathlib.Path = GEOMETRY_FILE_PATH.with_suffix(".preferences")
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

        # Screenshot overlay settings
        self._widgets.border_thickness = BorderThicknessSpinBox(initial_value=cfg.border_thickness)
        self._widgets.border_color = ColorEditPicker(initial_color=cfg.border_color)
        self._widgets.fill_color = ColorEditPicker(initial_color=cfg.fill_color)
        self._widgets.outline_color = ColorEditPicker(initial_color=cfg.outline_color)
        self._widgets.fill_brush_color = ColorEditPicker(initial_color=cfg.fill_brush_color)

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

    def _make_settings_layout(self) -> QLayout:
        """Build a form layout with labeled rows for each settings widget."""
        layout = QFormLayout()
        for key, widget in self._widgets.__dict__.items():
            layout.addRow(ui_translate(key), widget)
        return layout

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

        # Screenshot overlay settings
        self._cfg.border_thickness = self._widgets.border_thickness.value()
        self._cfg.border_color = self._widgets.border_color.color_hex()
        self._cfg.fill_color = self._widgets.fill_color.color_hex()
        self._cfg.outline_color = self._widgets.outline_color.color_hex()
        self._cfg.fill_brush_color = self._widgets.fill_brush_color.color_hex()

        try:
            self._cfg.save_to_file()
        except Exception as e:
            self.settings_applied.emit(SettingsApplyResult(error=e))
        else:
            self.settings_applied.emit(SettingsApplyResult(success=True, ocr_history=self.history_list.as_list()))
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

        # Screenshot overlay settings
        self._widgets.border_thickness.setValue(defaults.border_thickness)
        self._widgets.border_color.set_color(defaults.border_color)
        self._widgets.fill_color.set_color(defaults.fill_color)
        self._widgets.outline_color.set_color(defaults.outline_color)
        self._widgets.fill_brush_color.set_color(defaults.fill_brush_color)


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
