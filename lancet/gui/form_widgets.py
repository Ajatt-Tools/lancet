# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
from types import SimpleNamespace

from PyQt6.QtWidgets import QCheckBox

from lancet.config import Config
from lancet.gui.color_picker import ColorEditPicker
from lancet.gui.enum_select_combo import EnumSelectCombo
from lancet.gui.grab_key import ShortCutGrabButton
from lancet.gui.ocr_model_list import ModelListEditor
from lancet.gui.utils import SecondsSpinBox, DetectorInputSizeSpinBox, HistorySizeSpinBox, BorderThicknessSpinBox, \
    BindPortSpinBox


class FormWidgets(SimpleNamespace):
    """Container holding all form widgets used in the preferences dialog."""

    copy_to: EnumSelectCombo
    notification_duration: SecondsSpinBox
    huggingface_model: ModelListEditor
    force_cpu: QCheckBox
    recover_missed_text: QCheckBox
    text_detection_resolution: DetectorInputSizeSpinBox
    max_history_size: HistorySizeSpinBox
    show_help_bar: QCheckBox

    # Shortcuts
    ocr_shortcut: ShortCutGrabButton
    ocr_page_shortcut: ShortCutGrabButton
    screenshot_shortcut: ShortCutGrabButton

    # Screenshot overlay colors
    border_thickness: BorderThicknessSpinBox
    border_color: ColorEditPicker
    fill_color: ColorEditPicker
    outline_color: ColorEditPicker
    fill_brush_color: ColorEditPicker

    # Network
    bind_port: BindPortSpinBox


def create_form_widgets(cfg: Config) -> FormWidgets:
    widgets = FormWidgets()

    # OCR destination
    widgets.copy_to = EnumSelectCombo(initial_value=cfg.copy_to)

    # Notification duration
    widgets.notification_duration = SecondsSpinBox(initial_value=cfg.notification_duration_sec)

    # Huggingface model name
    widgets.huggingface_model = ModelListEditor()
    widgets.huggingface_model.set_items(cfg.huggingface_models)
    widgets.huggingface_model.set_current(cfg.huggingface_model_name)

    # Force CPU
    widgets.force_cpu = QCheckBox()
    widgets.force_cpu.setChecked(cfg.force_cpu)

    # Recover missed text
    widgets.recover_missed_text = QCheckBox()
    widgets.recover_missed_text.setChecked(cfg.recover_missed_text)

    # Text detection resolution
    widgets.text_detection_resolution = DetectorInputSizeSpinBox(initial_value=cfg.text_detection_resolution)

    # Show help bar
    widgets.show_help_bar = QCheckBox()
    widgets.show_help_bar.setChecked(cfg.show_help_bar)

    # OCR shortcut
    widgets.ocr_shortcut = ShortCutGrabButton(initial_value=cfg.ocr_shortcut)

    # OCR page shortcut (detect and OCR)
    widgets.ocr_page_shortcut = ShortCutGrabButton(initial_value=cfg.ocr_page_shortcut)

    # Screenshot shortcut
    widgets.screenshot_shortcut = ShortCutGrabButton(initial_value=cfg.screenshot_shortcut)

    # Max history size
    widgets.max_history_size = HistorySizeSpinBox(initial_value=cfg.max_history_size)

    # Bind port
    widgets.bind_port = BindPortSpinBox(initial_value=cfg.bind_port)

    # Screenshot overlay settings
    widgets.border_thickness = BorderThicknessSpinBox(initial_value=cfg.border_thickness)
    widgets.border_color = ColorEditPicker(initial_color=cfg.border_color)
    widgets.fill_color = ColorEditPicker(initial_color=cfg.fill_color)
    widgets.outline_color = ColorEditPicker(initial_color=cfg.outline_color)
    widgets.fill_brush_color = ColorEditPicker(initial_color=cfg.fill_brush_color)

    return widgets
