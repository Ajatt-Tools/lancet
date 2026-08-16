# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
import typing
from types import SimpleNamespace

from PyQt6.QtWidgets import QCheckBox

from lancet.config import Config
from lancet.gui.color_picker import ColorEditPicker
from lancet.gui.enum_select_combo import EnumSelectCombo
from lancet.gui.grab_key import ShortCutGrabButton
from lancet.gui.ocr_model_list import ModelListEditor
from lancet.gui.utils import (
    BindPortSpinBox,
    BorderThicknessSpinBox,
    DetectorInputSizeSpinBox,
    HistorySizeSpinBox,
    SecondsSpinBox,
)


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


class FormWidgetsBuilder:
    """Fluent builder that constructs all FormWidgets from a Config in grouped steps."""

    def __init__(self, cfg: Config) -> None:
        """Initialize the builder with the config to read initial widget values from."""
        self._cfg = cfg
        self._widgets = FormWidgets()

    def create_form_widgets(self) -> FormWidgets:
        """Create and return all form widgets used in the preferences dialog."""
        return (
            self.create_ocr_widgets()
            .create_shortcut_widgets()
            .create_overlay_widgets()
            .get_form()
        )

    def get_form(self) -> FormWidgets:
        """Return the assembled FormWidgets namespace."""
        return self._widgets

    def create_ocr_widgets(self) -> typing.Self:
        """Create OCR destination, notification, model, CPU, and detection widgets."""
        # OCR destination
        self._widgets.copy_to = EnumSelectCombo(initial_value=self._cfg.copy_to)
        # Notification duration
        self._widgets.notification_duration = SecondsSpinBox(initial_value=self._cfg.notification_duration_sec)
        # huggingface model name and items
        self._widgets.huggingface_model = ModelListEditor()
        self._widgets.huggingface_model.set_items(self._cfg.huggingface_models)
        self._widgets.huggingface_model.set_current(self._cfg.huggingface_model_name)
        # Force CPU
        self._widgets.force_cpu = QCheckBox()
        self._widgets.force_cpu.setChecked(self._cfg.force_cpu)
        # Recover missed text
        self._widgets.recover_missed_text = QCheckBox()
        self._widgets.recover_missed_text.setChecked(self._cfg.recover_missed_text)
        # Text detection resolution
        self._widgets.text_detection_resolution = DetectorInputSizeSpinBox(
            initial_value=self._cfg.text_detection_resolution
        )
        # Show help bar
        self._widgets.show_help_bar = QCheckBox()
        self._widgets.show_help_bar.setChecked(self._cfg.show_help_bar)
        return self

    def create_shortcut_widgets(self) -> typing.Self:
        """Create keyboard shortcut grab buttons from the config."""
        # OCR shortcut
        self._widgets.ocr_shortcut = ShortCutGrabButton(initial_value=self._cfg.ocr_shortcut)
        # OCR page shortcut (detect and OCR)
        self._widgets.ocr_page_shortcut = ShortCutGrabButton(initial_value=self._cfg.ocr_page_shortcut)
        # Screenshot shortcut
        self._widgets.screenshot_shortcut = ShortCutGrabButton(initial_value=self._cfg.screenshot_shortcut)
        return self

    def create_overlay_widgets(self) -> typing.Self:
        """Create screenshot overlay, history, and network widgets."""
        # Max history size
        self._widgets.max_history_size = HistorySizeSpinBox(initial_value=self._cfg.max_history_size)
        # Bind port
        self._widgets.bind_port = BindPortSpinBox(initial_value=self._cfg.bind_port)
        # Screenshot overlay settings
        self._widgets.border_thickness = BorderThicknessSpinBox(initial_value=self._cfg.border_thickness)
        self._widgets.border_color = ColorEditPicker(initial_color=self._cfg.border_color)
        self._widgets.fill_color = ColorEditPicker(initial_color=self._cfg.fill_color)
        self._widgets.outline_color = ColorEditPicker(initial_color=self._cfg.outline_color)
        self._widgets.fill_brush_color = ColorEditPicker(initial_color=self._cfg.fill_brush_color)
        return self
