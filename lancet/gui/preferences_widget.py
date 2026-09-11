# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
import typing
from collections.abc import Iterable, Set

from PyQt6.QtWidgets import QFormLayout, QTabWidget, QWidget

from lancet.config import Config
from lancet.consts import DEFAULT_ANKICONNECT_URL
from lancet.gui.form_widgets import FormWidgets, FormWidgetsBuilder
from lancet.gui.utils import ui_translate
from lancet.gui.widgets_to_config_dict import (
    get_from_widget,
    set_cfg_value,
    set_from_cfg,
)

# Keys that cannot be handled by the generic loop because one widget maps to
# multiple config fields, or the widget key does not match a config field.
SPECIAL_KEYS: typing.Final[frozenset[str]] = frozenset({"huggingface_model", "anki_image_settings"})
ADVANCED_KEYS: typing.Final[frozenset[str]] = frozenset(
    {
        "huggingface_model",
        "recover_missed_text",
        "text_detection_resolution",
        "bind_port",
        "path_to_goldendict_executable",
    }
)
ANKI_KEYS: typing.Final[frozenset[str]] = frozenset(
    {
        # anki_shortcut is excluded from here and shown in the Main (General) tab with other shortcuts.
        "anki_connect_url",
        "anki_connect_api_key",
        "anki_image_field",
        "anki_image_format",
        "anki_image_settings",
    }
)


class FormWidgetEntry(typing.NamedTuple):
    """A Config field name and its corresponding preferences widget."""

    cfg_key: str
    widget: QWidget


def filter_dict[K, V](d: dict[K, V], keys: Set[K]) -> dict[K, V]:
    """Return a new dict containing only keys from the requested set, preserving original order."""
    # Preserve order of keys.
    return {key: value for key, value in d.items() if key in keys}


def iter_widgets(widgets: FormWidgets) -> Iterable[FormWidgetEntry]:
    """Yield widgets that directly map to one Config field, preserving form order."""
    for key, widget in widgets.__dict__.items():
        if key not in SPECIAL_KEYS:
            yield FormWidgetEntry(cfg_key=key, widget=widget)


def label_replace(cfg_key: str) -> str:
    """Map a config key to a prettier key used for generating UI labels."""
    match cfg_key:
        case "notification_duration_sec":
            return "notification_duration"
        case "path_to_goldendict_executable":
            return "goldendict_executable"
        case "anki_connect_url":
            return "AnkiConnect URL"
        case "anki_connect_api_key":
            return "AnkiConnect API key"
        case "anki_image_field":
            return "Image field"
        case "anki_image_format":
            return "Image format"
        case "anki_image_settings":
            return "Image size and quality"
        case _:
            return cfg_key


def make_tab(widgets: dict[str, QWidget]) -> QWidget:
    """Build a QWidget tab containing translated form rows for the provided widgets."""
    tab = QWidget()
    tab.setLayout(layout := QFormLayout())
    for key, widget in widgets.items():
        layout.addRow(ui_translate(label_replace(key)), widget)
    return tab


class CopySettingsFromWidgetsToConfig:
    """Copy current values from all form widgets back into the Config object."""

    def __init__(self, cfg: Config, widgets: FormWidgets) -> None:
        """Store references to the config and the form widgets to read from."""
        self._cfg = cfg
        self._widgets = widgets

    def copy_settings_to_cfg(self) -> typing.Self:
        """Copy all current widget values into the backing Config object."""
        for cfg_key, widget in iter_widgets(self._widgets):
            set_cfg_value(self._cfg, cfg_key, get_from_widget(widget))
        # Special case: huggingface_model maps to two config fields.
        self._cfg.huggingface_model_name = self._widgets.huggingface_model.current_text()
        self._cfg.huggingface_models = self._widgets.huggingface_model.models_as_list()
        anki_settings = self._widgets.anki_image_settings.values()
        self._cfg.anki_image_width = anki_settings.width
        self._cfg.anki_image_height = anki_settings.height
        self._cfg.anki_image_quality = anki_settings.quality
        return self


class FormWidgetsToolTips:
    """Set tooltips on all form widgets, grouped by category."""

    def __init__(self, widgets: FormWidgets) -> None:
        """Store a reference to the form widgets to apply tooltips to."""
        self._widgets = widgets

    def add_tooltips(self) -> typing.Self:
        """Set tooltips on all widgets, grouped by category."""
        return (
            self._add_main_tooltips()
            ._add_shortcut_tooltips()
            ._add_anki_tooltips()
            ._add_paths_tooltips()
            ._add_overlay_tooltips()
        )

    def _add_main_tooltips(self) -> typing.Self:
        """Set tooltips on general OCR, model, and history widgets."""
        self._widgets.copy_to.setToolTip("Destination for recognized text.")
        self._widgets.notification_duration_sec.setToolTip("Duration in seconds to show notifications.")
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
        self._widgets.anki_shortcut.setToolTip(
            "Keyboard shortcut to attach a selected screen region to the last Anki note."
        )
        return self

    def _add_anki_tooltips(self) -> typing.Self:
        """Set tooltips on AnkiConnect and image-encoding widgets."""
        self._widgets.anki_connect_url.setToolTip(
            f"AnkiConnect endpoint. AnkiConnect defaults to {DEFAULT_ANKICONNECT_URL}."
        )
        self._widgets.anki_connect_api_key.setToolTip(
            "Optional AnkiConnect API key. It is masked here but stored in Lancet's plaintext JSON config."
        )
        self._widgets.anki_image_field.setToolTip("The Anki note field where selected images are appended.")
        self._widgets.anki_image_format.setToolTip("The image format used to encode uploaded Anki media.")
        return self

    def _add_paths_tooltips(self) -> typing.Self:
        """Set tooltips on Path widgets."""
        self._widgets.path_to_goldendict_executable.set_tooltip(
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
    """Populate form widgets with values from a Config object."""

    def __init__(self, cfg: Config, widgets: FormWidgets) -> None:
        """Store references to the config and the form widgets to populate."""
        self._cfg = cfg
        self._widgets = widgets

    def set_widget_values(self) -> typing.Self:
        """Populate all widgets with values from the config object."""
        for cfg_key, widget in iter_widgets(self._widgets):
            set_from_cfg(widget, getattr(self._cfg, cfg_key))
        # Special case: huggingface_model maps to two config fields.
        self._widgets.huggingface_model.set_items(self._cfg.huggingface_models)
        self._widgets.huggingface_model.set_current(self._cfg.huggingface_model_name)
        self._widgets.anki_image_settings.set_values(
            width=self._cfg.anki_image_width,
            height=self._cfg.anki_image_height,
            quality=self._cfg.anki_image_quality,
        )
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
        self.addTab(make_tab(filter_dict(d, d.keys() - ADVANCED_KEYS - ANKI_KEYS)), "Main")
        self.addTab(make_tab(filter_dict(d, ANKI_KEYS)), "Anki")
        self.addTab(make_tab(filter_dict(d, ADVANCED_KEYS)), "Advanced")

    def copy_settings_to_cfg(self) -> None:
        """Copy all current widget values into the backing Config object."""
        CopySettingsFromWidgetsToConfig(self._cfg, self._widgets).copy_settings_to_cfg()

    def add_tooltips(self) -> None:
        """Set tooltips on all preference widgets."""
        FormWidgetsToolTips(self._widgets).add_tooltips()

    def set_widget_values(self, values: Config) -> None:
        """Populate all widgets with values from the config object."""
        FormWidgetValues(values, self._widgets).set_widget_values()
