# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
import dataclasses
import sys

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
)

from lancet.config import Config
from lancet.consts import APP_NAME, APP_LOGO_PATH
from lancet.gui.enum_select_combo import EnumSelectCombo
from lancet.gui.grab_key import ShortCutGrabButton
from lancet.gui.ocr_model_list import ModelListEditor


@dataclasses.dataclass(frozen=True)
class SettingsApplyResult:
    success: bool = False
    error: Exception | None = None


def ui_translate(key: str) -> str:
    return key.capitalize().replace("_", " ")


class SecondsSpinBox(QSpinBox):
    min: int = 1
    max: int = 120

    def __init__(self, initial_value: int, parent=None):
        super().__init__(parent)
        self.setRange(self.min, self.max)
        self.setSuffix(" seconds")
        self.setValue(initial_value)


class FormWidgets:
    copy_to: EnumSelectCombo
    notification_duration: SecondsSpinBox
    huggingface_model: ModelListEditor
    force_cpu: QCheckBox
    ocr_shortcut: ShortCutGrabButton
    screenshot_shortcut: ShortCutGrabButton


class PreferencesDialog(QDialog):
    """Preferences dialog for editing all Config fields."""

    settings_applied = pyqtSignal(SettingsApplyResult)

    def __init__(self, cfg: Config, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cfg = cfg

        self.setWindowIcon(QIcon(str(APP_LOGO_PATH)))
        self.setWindowTitle(f"{APP_NAME} Preferences")
        self.setMinimumWidth(450)

        main_layout = QVBoxLayout()
        self.setLayout(main_layout)
        self._widgets = FormWidgets()

        # OCR destination
        self._widgets.copy_to = EnumSelectCombo(initial_value=self._cfg.copy_to)

        # Notification duration
        self._widgets.notification_duration = SecondsSpinBox(initial_value=self._cfg.notification_duration_sec)

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

        # Set Preferences layout
        main_layout.addLayout(self._make_settings_layout())

        # Dialog buttons
        self._button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Apply
            | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.RestoreDefaults
        )
        self._button_box.clicked.connect(self._on_button_clicked)
        main_layout.addWidget(self._button_box)

    def _make_settings_layout(self) -> QLayout:
        layout = QFormLayout()
        for key, widget in self._widgets.__dict__.items():
            layout.addRow(ui_translate(key), widget)
        return layout

    def _on_button_clicked(self, button: QAbstractButton) -> None:
        match self._button_box.buttonRole(button):
            case QDialogButtonBox.ButtonRole.ApplyRole:
                self._apply()
            case QDialogButtonBox.ButtonRole.RejectRole:
                self.reject()
            case QDialogButtonBox.ButtonRole.ResetRole:
                self._restore_defaults()

    def _apply(self) -> None:
        self._cfg.copy_to = self._widgets.copy_to.currentData()
        self._cfg.notification_duration_sec = self._widgets.notification_duration.value()
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
        self.accept()

    def _restore_defaults(self) -> None:
        defaults = Config()
        self._widgets.copy_to.set_current(defaults.copy_to)
        self._widgets.notification_duration.setValue(defaults.notification_duration_sec)
        self._widgets.huggingface_model.set_current(defaults.huggingface_model_name)
        self._widgets.huggingface_model.set_items(defaults.huggingface_models)
        self._widgets.force_cpu.setChecked(defaults.force_cpu)
        self._widgets.ocr_shortcut.set_keyboard_shortcut(defaults.ocr_shortcut)
        self._widgets.screenshot_shortcut.set_keyboard_shortcut(defaults.screenshot_shortcut)


def playground():
    app = QApplication(sys.argv)
    cfg = Config.read_from_file()
    form = PreferencesDialog(cfg)
    form.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    playground()
