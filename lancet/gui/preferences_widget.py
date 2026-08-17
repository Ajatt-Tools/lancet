# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
import typing

from PyQt6.QtWidgets import QFormLayout, QTabWidget, QWidget

from lancet.config import Config
from lancet.gui.form_widgets import FormWidgets, FormWidgetsBuilder
from lancet.gui.utils import ui_translate
from lancet.model_utils.common import round_to_stride


def filter_dict[K, V](d: dict[K, V], keys: set[K]) -> dict[K, V]:
    """Return a new dict containing only keys from the requested set, preserving original order."""
    # Preserve order of keys.
    return {key: value for key, value in d.items() if key in keys}


def make_tab(widgets: dict[str, QWidget]) -> QWidget:
    """Build a QWidget tab containing translated form rows for the provided widgets."""
    tab = QWidget()
    tab.setLayout(layout := QFormLayout())
    for key, widget in widgets.items():
        layout.addRow(ui_translate(key), widget)
    return tab


class CopySettingsFromWidgetsToConfig:
    def __init__(self, cfg: Config, widgets: FormWidgets) -> None:
        self._cfg = cfg
        self._widgets = widgets

    def copy_settings_to_cfg(self) -> typing.Self:
        """Copy all current widget values into the backing Config object."""
        return (
            self._copy_main_settings_to_cfg()
            ._copy_shortcuts_to_cfg()
            ._copy_paths_to_cfg()
            ._copy_overlay_settings_to_cfg()
        )

    def _copy_main_settings_to_cfg(self) -> typing.Self:
        """Copy general OCR and history settings into the config."""
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
        return self

    def _copy_shortcuts_to_cfg(self) -> typing.Self:
        """Copy keyboard shortcut settings into the config."""
        self._cfg.ocr_shortcut = self._widgets.ocr_shortcut.current_shortcut()
        self._cfg.ocr_page_shortcut = self._widgets.ocr_page_shortcut.current_shortcut()
        self._cfg.screenshot_shortcut = self._widgets.screenshot_shortcut.current_shortcut()
        return self

    def _copy_paths_to_cfg(self) -> typing.Self:
        """Copy path settings into the config."""
        self._cfg.path_to_goldendict_executable = self._widgets.goldendict_executable.get_file_path()
        return self

    def _copy_overlay_settings_to_cfg(self) -> typing.Self:
        """Copy screenshot overlay color and sizing settings into the config."""
        self._cfg.border_thickness = self._widgets.border_thickness.value()
        self._cfg.border_color = self._widgets.border_color.color_hex()
        self._cfg.fill_color = self._widgets.fill_color.color_hex()
        self._cfg.outline_color = self._widgets.outline_color.color_hex()
        self._cfg.fill_brush_color = self._widgets.fill_brush_color.color_hex()
        return self


class FormWidgetsToolTips:
    def __init__(self, widgets: FormWidgets) -> None:
        self._widgets = widgets

    def add_tooltips(self) -> typing.Self:
        return self._add_main_tooltips()._add_shortcut_tooltips()._add_paths_tooltips()._add_overlay_tooltips()

    def _add_main_tooltips(self) -> typing.Self:
        """Set tooltips on general OCR, model, and history widgets."""
        self._widgets.copy_to.setToolTip("Destination for recognized text.")
        self._widgets.notification_duration.setToolTip("Duration in seconds to show notifications.")
        self._widgets.huggingface_model.setToolTip("Huggingface model to use for OCR.")
        self._widgets.force_cpu.setToolTip("Recognize text on images using CPU instead of CUDA.")
        self._widgets.show_help_bar.setToolTip("Show the help bar in the main window.")
        self._widgets.max_history_size.setToolTip("Maximum number of OCR history entries to keep.")
        self._widgets.bind_port.setToolTip("Port number for the server to bind to.")
        self._widgets.recover_missed_text.setToolTip(
            "Recover text regions found by segmentation,\nbut missed by the bounding-box detector.\n"
            "Disabling reduces false positives but may miss some text."
        )
        self._widgets.text_detection_resolution.setToolTip(
            "Resolution in pixels for text detection. " "Larger values detect smaller text but are slower."
        )
        return self

    def _add_shortcut_tooltips(self) -> typing.Self:
        """Set tooltips on keyboard shortcut widgets."""
        self._widgets.ocr_shortcut.setToolTip("Keyboard shortcut to trigger OCR.")
        self._widgets.ocr_page_shortcut.setToolTip("Keyboard shortcut to detect speech bubbles and run OCR.")
        self._widgets.screenshot_shortcut.setToolTip("Keyboard shortcut to take a screenshot.")
        return self

    def _add_paths_tooltips(self) -> typing.Self:
        """Set tooltips on Path widgets."""
        self._widgets.goldendict_executable.set_tooltip(
            "GoldenDict binary used for OCR lookup.\n" "Leave empty to call: goldendict."
        )
        return self

    def _add_overlay_tooltips(self) -> typing.Self:
        """Set tooltips on screenshot overlay widgets."""
        self._widgets.border_thickness.setToolTip("Thickness of the selection border in pixels.")
        self._widgets.border_color.setToolTip("Color of the selection border.")
        self._widgets.fill_color.setToolTip("Fill color for the selected area.")
        self._widgets.outline_color.setToolTip("Color of the text outline.")
        self._widgets.fill_brush_color.setToolTip("Color of the fill brush.")
        return self


class FormWidgetValues:
    def __init__(self, cfg: Config, widgets: FormWidgets) -> None:
        self._cfg = cfg
        self._widgets = widgets

    def set_widget_values(self) -> typing.Self:
        """Populate all widgets with values from the config object."""
        return (
            self._set_main_widget_values()
            ._set_shortcut_widget_values()
            ._set_path_widget_values()
            ._set_overlay_widget_values()
        )

    def _set_main_widget_values(self) -> typing.Self:
        """Populate general OCR and history widgets from config values."""
        self._widgets.copy_to.set_current(self._cfg.copy_to)
        self._widgets.notification_duration.setValue(self._cfg.notification_duration_sec)
        self._widgets.max_history_size.setValue(self._cfg.max_history_size)
        self._widgets.bind_port.setValue(self._cfg.bind_port)
        self._widgets.huggingface_model.set_current(self._cfg.huggingface_model_name)
        self._widgets.huggingface_model.set_items(self._cfg.huggingface_models)
        self._widgets.force_cpu.setChecked(self._cfg.force_cpu)
        self._widgets.recover_missed_text.setChecked(self._cfg.recover_missed_text)
        self._widgets.text_detection_resolution.setValue(self._cfg.text_detection_resolution)
        self._widgets.show_help_bar.setChecked(self._cfg.show_help_bar)
        return self

    def _set_shortcut_widget_values(self) -> typing.Self:
        """Populate keyboard shortcut widgets from config values."""
        self._widgets.ocr_shortcut.set_keyboard_shortcut(self._cfg.ocr_shortcut)
        self._widgets.ocr_page_shortcut.set_keyboard_shortcut(self._cfg.ocr_page_shortcut)
        self._widgets.screenshot_shortcut.set_keyboard_shortcut(self._cfg.screenshot_shortcut)
        return self

    def _set_path_widget_values(self) -> typing.Self:
        """Populate Path widgets from config values."""
        self._widgets.goldendict_executable.set_file_path(self._cfg.path_to_goldendict_executable)
        return self

    def _set_overlay_widget_values(self) -> typing.Self:
        """Populate screenshot overlay widgets from config values."""
        self._widgets.border_thickness.setValue(self._cfg.border_thickness)
        self._widgets.border_color.set_color(self._cfg.border_color)
        self._widgets.fill_color.set_color(self._cfg.fill_color)
        self._widgets.outline_color.set_color(self._cfg.outline_color)
        self._widgets.fill_brush_color.set_color(self._cfg.fill_brush_color)
        return self


class MainPreferencesWidget(QTabWidget):
    """Tabbed preferences widget that edits and applies Config values."""

    def __init__(self, cfg: Config, parent: QWidget | None = None) -> None:
        """Initialize preferences tabs from the provided config."""
        super().__init__(parent)
        self._cfg = cfg
        self._widgets = FormWidgetsBuilder(cfg).create_form_widgets()
        self._setup_tabs()

    @property
    def widgets(self) -> FormWidgets:
        """Return the constructed form widgets."""
        return self._widgets

    def _setup_tabs(self) -> None:
        """Build a form layout with labeled rows for each settings widget."""
        d = self._widgets.__dict__
        advanced = {
            "huggingface_model",
            "recover_missed_text",
            "text_detection_resolution",
            "bind_port",
            "goldendict_executable",
        }

        self.addTab(make_tab(filter_dict(d, d.keys() - advanced)), "Main")
        self.addTab(make_tab(filter_dict(d, advanced)), "Advanced")

    def copy_settings_to_cfg(self) -> None:
        """Copy all current widget values into the backing Config object."""
        CopySettingsFromWidgetsToConfig(self._cfg, self._widgets).copy_settings_to_cfg()

    def add_tooltips(self) -> None:
        """Set tooltips on all preference widgets."""
        FormWidgetsToolTips(self._widgets).add_tooltips()

    def set_widget_values(self, values: Config) -> None:
        """Populate all widgets with values from the config object."""
        FormWidgetValues(values, self._widgets).set_widget_values()
