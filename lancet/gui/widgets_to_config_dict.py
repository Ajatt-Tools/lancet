# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
import enum

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QLineEdit,
    QPlainTextEdit,
    QSpinBox,
    QWidget,
)

from lancet.config import Config
from lancet.gui.color_picker import ColorEditPicker
from lancet.gui.enum_select_combo import EnumSelectCombo
from lancet.gui.file_picker import LancetFilePicker
from lancet.gui.grab_key import ShortCutGrabButton
from lancet.gui.utils import DetectorInputSizeSpinBox

type CfgValueTypes = bool | str | int | float | enum.Enum


def set_from_cfg(widget: QWidget, value: CfgValueTypes) -> None:
    """Set a widget's value from a configuration value based on the widget type."""
    match widget:
        case LancetFilePicker() if isinstance(value, str):
            widget.set_file_path(value)
        case ShortCutGrabButton() if isinstance(value, str):
            widget.set_keyboard_shortcut(value)
        case ColorEditPicker() if isinstance(value, str):
            widget.set_color(value)
        case QDoubleSpinBox() if isinstance(value, (int, float)):
            widget.setValue(value)
        case QSpinBox() if isinstance(value, int):
            widget.setValue(value)
        case QLineEdit() if isinstance(value, str):
            widget.setText(value)
        case QCheckBox() if isinstance(value, bool):
            widget.setChecked(value)
        case EnumSelectCombo() if isinstance(value, enum.Enum):
            widget.set_current(value)
        case QComboBox() if isinstance(value, str):
            widget.setCurrentText(value)
        case QPlainTextEdit() if isinstance(value, str):
            widget.setPlainText(value)
        case _:
            raise ValueError(
                f"Can't handle widget of type {type(widget).__name__} and value of type {type(value).__name__}"
            )


def get_from_widget(widget: QWidget) -> CfgValueTypes:
    """Extract the current value from a widget based on its type."""
    match widget:
        case LancetFilePicker():
            return widget.get_file_path()
        case DetectorInputSizeSpinBox():
            return widget.rounded_value()
        case EnumSelectCombo():
            return widget.currentData()
        case QDoubleSpinBox() | QSpinBox():
            return widget.value()
        case ColorEditPicker():
            return widget.color_hex()
        case QComboBox():
            return widget.currentText()
        case QLineEdit():
            return widget.text()
        case QCheckBox():
            return widget.isChecked()
        case ShortCutGrabButton():
            return widget.current_shortcut()
        case QPlainTextEdit():
            return widget.toPlainText()
    raise ValueError(f"Don't know how to handle widget of type {type(widget).__name__}.")


def set_cfg_value(cfg: Config, cfg_key: str, new_value: CfgValueTypes) -> None:
    """Set a Config attribute after verifying the key exists and its value type matches."""
    if not hasattr(cfg, cfg_key):
        raise AttributeError(f"config has no attribute '{cfg_key}'")
    old_value = getattr(cfg, cfg_key)
    if not isinstance(new_value, type(old_value)):
        raise TypeError(f"types differ in widget and config: {type(old_value)} != {type(new_value)}")
    setattr(cfg, cfg_key, new_value)
