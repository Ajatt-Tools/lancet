# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
from PyQt6.QtWidgets import QWidget, QFormLayout, QTabWidget

from lancet.config import Config
from lancet.gui.form_widgets import create_form_widgets, FormWidgets

from lancet.gui.utils import ui_translate
from lancet.model_utils.common import round_to_stride


def filter_dict[K, V](d: dict[K, V], keys: set[K]) -> dict[K, V]:
    # Preserve order of keys.
    return {key: value for key, value in d.items() if key in keys}


def make_tab(widgets: dict[str, QWidget]) -> QWidget:
    tab = QWidget()
    tab.setLayout(layout := QFormLayout())
    for key, widget in widgets.items():
        layout.addRow(ui_translate(key), widget)
    return tab


class MainPreferencesWidget(QTabWidget):
    def __init__(self, cfg: Config, parent: QWidget | None = None):
        super().__init__(parent)
        self._cfg = cfg
        self._widgets = create_form_widgets(cfg)
        self._setup_tabs()

    @property
    def widgets(self) -> FormWidgets:
        return self._widgets

    def _setup_tabs(self) -> None:
        """Build a form layout with labeled rows for each settings widget."""
        d = self._widgets.__dict__
        advanced = {
            "huggingface_model",
            "recover_missed_text",
            "text_detection_resolution",
            "bind_port",
        }

        self.addTab(make_tab(filter_dict(d, d.keys() - advanced)), "Main")
        self.addTab(make_tab(filter_dict(d, advanced)), "Advanced")

    def copy_settings_to_cfg(self) -> None:
        self._cfg.copy_to = self._widgets.copy_to.currentData()
        self._cfg.notification_duration_sec = self._widgets.notification_duration.value()
        self._cfg.max_history_size = self._widgets.max_history_size.value()
        self._cfg.bind_port = self._widgets.bind_port.value()
        self._cfg.huggingface_model_name = self._widgets.huggingface_model.current_text()
        self._cfg.huggingface_models = self._widgets.huggingface_model.models_as_list()
        self._cfg.force_cpu = self._widgets.force_cpu.isChecked()
        self._cfg.show_help_bar = self._widgets.show_help_bar.isChecked()
        self._cfg.recover_missed_text = self._widgets.recover_missed_text.isChecked()
        self._cfg.text_detection_resolution = round_to_stride(self._widgets.text_detection_resolution.value())

        # Shortcuts
        self._cfg.ocr_shortcut = self._widgets.ocr_shortcut.current_shortcut()
        self._cfg.ocr_page_shortcut = self._widgets.ocr_page_shortcut.current_shortcut()
        self._cfg.screenshot_shortcut = self._widgets.screenshot_shortcut.current_shortcut()

        # Screenshot overlay settings
        self._cfg.border_thickness = self._widgets.border_thickness.value()
        self._cfg.border_color = self._widgets.border_color.color_hex()
        self._cfg.fill_color = self._widgets.fill_color.color_hex()
        self._cfg.outline_color = self._widgets.outline_color.color_hex()
        self._cfg.fill_brush_color = self._widgets.fill_brush_color.color_hex()

    def add_tooltips(self) -> None:
        self._widgets.copy_to.setToolTip("Destination for recognized text.")
        self._widgets.notification_duration.setToolTip("Duration in seconds to show notifications.")
        self._widgets.huggingface_model.setToolTip("Huggingface model to use for OCR.")
        self._widgets.force_cpu.setToolTip("Recognize text on images using CPU instead of CUDA.")
        self._widgets.show_help_bar.setToolTip("Show the help bar in the main window.")
        self._widgets.ocr_shortcut.setToolTip("Keyboard shortcut to trigger OCR.")
        self._widgets.ocr_page_shortcut.setToolTip("Keyboard shortcut to detect speech bubbles and run OCR.")
        self._widgets.screenshot_shortcut.setToolTip("Keyboard shortcut to take a screenshot.")
        self._widgets.max_history_size.setToolTip("Maximum number of OCR history entries to keep.")
        self._widgets.bind_port.setToolTip("Port number for the server to bind to.")
        self._widgets.border_thickness.setToolTip("Thickness of the selection border in pixels.")
        self._widgets.border_color.setToolTip("Color of the selection border.")
        self._widgets.fill_color.setToolTip("Fill color for the selected area.")
        self._widgets.outline_color.setToolTip("Color of the text outline.")
        self._widgets.fill_brush_color.setToolTip("Color of the fill brush.")
        self._widgets.recover_missed_text.setToolTip(
            "Recover text regions found by segmentation,\nbut missed by the bounding-box detector.\n"
            "Disabling reduces false positives but may miss some text."
        )
        self._widgets.text_detection_resolution.setToolTip(
            "Resolution in pixels for text detection. " "Larger values detect smaller text but are slower."
        )

    def set_widget_values(self, values: Config) -> None:
        self._widgets.copy_to.set_current(values.copy_to)
        self._widgets.notification_duration.setValue(values.notification_duration_sec)
        self._widgets.max_history_size.setValue(values.max_history_size)
        self._widgets.bind_port.setValue(values.bind_port)
        self._widgets.huggingface_model.set_current(values.huggingface_model_name)
        self._widgets.huggingface_model.set_items(values.huggingface_models)
        self._widgets.force_cpu.setChecked(values.force_cpu)
        self._widgets.recover_missed_text.setChecked(values.recover_missed_text)
        self._widgets.text_detection_resolution.setValue(values.text_detection_resolution)
        self._widgets.show_help_bar.setChecked(values.show_help_bar)

        # Shortcuts
        self._widgets.ocr_shortcut.set_keyboard_shortcut(values.ocr_shortcut)
        self._widgets.ocr_page_shortcut.set_keyboard_shortcut(values.ocr_page_shortcut)
        self._widgets.screenshot_shortcut.set_keyboard_shortcut(values.screenshot_shortcut)

        # Screenshot overlay settings
        self._widgets.border_thickness.setValue(values.border_thickness)
        self._widgets.border_color.set_color(values.border_color)
        self._widgets.fill_color.set_color(values.fill_color)
        self._widgets.outline_color.set_color(values.outline_color)
        self._widgets.fill_brush_color.set_color(values.fill_brush_color)
