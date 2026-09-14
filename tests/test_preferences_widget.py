# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import dataclasses
import typing
from collections.abc import Callable, Sequence

import pytest
from PyQt6.QtWidgets import QApplication, QFormLayout, QLabel

from lancet.anki.image_types import AnkiImageFormat
from lancet.config import Config, OcrDestination
from lancet.gui.form_widgets import FormWidgets, FormWidgetsBuilder
from lancet.gui.preferences_widget import (
    ANKI_KEYS,
    SPECIAL_KEYS,
    CopySettingsFromWidgetsToConfig,
    FormWidgetValues,
    MainPreferencesWidget,
    label_replace,
)
from lancet.gui.widgets_to_config_dict import set_from_cfg


class FieldParityScenario(typing.NamedTuple):
    """Exceptional form fields and the Config fields they represent."""

    special_widget_fields: frozenset[str]
    represented_config_fields: frozenset[str]


FIELD_PARITY_SCENARIOS: dict[str, FieldParityScenario] = {
    "composite_widgets": FieldParityScenario(
        special_widget_fields=frozenset({"huggingface_model", "anki_image_settings"}),
        represented_config_fields=frozenset(
            {
                "huggingface_model_name",
                "huggingface_models",
                "anki_image_width",
                "anki_image_height",
                "anki_image_quality",
            }
        ),
    )
}


class TestFormWidgetFieldParity:
    """Ensure every Config field has a corresponding form widget."""

    @pytest.mark.parametrize("scenario", FIELD_PARITY_SCENARIOS.values(), ids=FIELD_PARITY_SCENARIOS.keys())
    def test_fields_match(self, scenario: FieldParityScenario) -> None:
        """Generic and special widgets together represent every Config field."""
        form_fields = frozenset(FormWidgets.__annotations__)
        config_fields = frozenset(field.name for field in dataclasses.fields(Config))
        assert SPECIAL_KEYS == scenario.special_widget_fields
        assert form_fields - scenario.special_widget_fields == config_fields - scenario.represented_config_fields


class ConfigScenario(typing.NamedTuple):
    """A fresh configuration factory used to prevent mutable scenario state leakage."""

    create: Callable[[], Config]


def make_round_trip_config() -> Config:
    """Create a configuration with non-default values for every preferences control.

    The single declarative constructor makes the complete form contract visible;
    splitting it by UI section would obscure which settings the round trip covers.
    """
    return Config(
        copy_to=OcrDestination.clipboard,
        notification_duration_sec=17,
        huggingface_model_name="custom/model",
        huggingface_models=["base/model", "custom/model"],
        force_cpu=True,
        recover_missed_text=False,
        text_detection_resolution=1152,
        max_history_size=321,
        show_help_bar=False,
        ocr_shortcut="Ctrl+Shift+J",
        ocr_page_shortcut="Alt+P",
        screenshot_shortcut="Meta+S",
        anki_shortcut="Ctrl+Shift+A",
        anki_connect_url="http://localhost:8765",
        anki_connect_api_key="secret",
        anki_image_field="AnkiImage",
        anki_field_separator="<hr>",
        anki_image_width=600,
        anki_image_height=400,
        anki_image_quality=77,
        anki_image_format=AnkiImageFormat.webp,
        path_to_goldendict_executable="/opt/goldendict",
        border_thickness=7,
        border_color="#AA112233",
        fill_color="#BB223344",
        outline_color="#CC334455",
        fill_brush_color="#DD445566",
        bind_port=23456,
    )


ROUND_TRIP_SCENARIOS: dict[str, ConfigScenario] = {
    "non_default_values": ConfigScenario(create=make_round_trip_config),
}


class TestConfigFormRoundTrip:
    """Test complete Config-to-widget-to-Config conversion."""

    @pytest.mark.parametrize("scenario", ROUND_TRIP_SCENARIOS.values(), ids=ROUND_TRIP_SCENARIOS.keys())
    def test_round_trip(self, scenario: ConfigScenario, qapp: QApplication) -> None:
        """All configuration fields survive conversion through form widgets."""
        source = scenario.create()
        target = Config()
        widgets = FormWidgetsBuilder(target).create_form_widgets()
        FormWidgetValues(source, widgets).set_widget_values()
        CopySettingsFromWidgetsToConfig(target, widgets).copy_settings_to_cfg()
        assert dataclasses.asdict(target) == dataclasses.asdict(source)


class LabelReplaceScenario(typing.NamedTuple):
    """A Config field name and its expected display-label key."""

    cfg_key: str
    expected: str


LABEL_REPLACE_SCENARIOS: dict[str, LabelReplaceScenario] = {
    "sec_suffix": LabelReplaceScenario(cfg_key="notification_duration_sec", expected="notification_duration"),
    "goldendict_prefix": LabelReplaceScenario(
        cfg_key="path_to_goldendict_executable", expected="goldendict_executable"
    ),
    "anki_separator": LabelReplaceScenario(cfg_key="anki_field_separator", expected="Field separator"),
    "passthrough_simple": LabelReplaceScenario(cfg_key="border_thickness", expected="border_thickness"),
    "passthrough_copy_to": LabelReplaceScenario(cfg_key="copy_to", expected="copy_to"),
    "passthrough_shortcut": LabelReplaceScenario(cfg_key="ocr_shortcut", expected="ocr_shortcut"),
}


class TestLabelReplace:
    """Test config-key mapping to display-label keys."""

    @pytest.mark.parametrize("scenario", LABEL_REPLACE_SCENARIOS.values(), ids=LABEL_REPLACE_SCENARIOS.keys())
    def test_replace(self, scenario: LabelReplaceScenario) -> None:
        """Each config key maps to its expected display key."""
        assert label_replace(scenario.cfg_key) == scenario.expected


class AnkiTabScenario(typing.NamedTuple):
    """Expected tab titles and ownership of Anki image/connection controls."""

    tab_titles: Sequence[str]
    anki_keys: frozenset[str]


ANKI_TAB_SCENARIOS: dict[str, AnkiTabScenario] = {
    "connection_and_image_settings": AnkiTabScenario(
        tab_titles=("Main", "Anki", "Advanced"),
        anki_keys=frozenset(
            {
                "anki_connect_url",
                "anki_connect_api_key",
                "anki_image_field",
                "anki_field_separator",
                "anki_image_format",
                "anki_image_settings",
            }
        ),
    ),
}


class TestAnkiPreferencesTab:
    """Test the dedicated Preferences tab for Anki connection and image controls."""

    @pytest.mark.parametrize("scenario", ANKI_TAB_SCENARIOS.values(), ids=ANKI_TAB_SCENARIOS.keys())
    def test_anki_widget_ownership(self, scenario: AnkiTabScenario, qapp: QApplication) -> None:
        """Anki image/connection widgets belong to the Anki tab while its shortcut stays on Main."""
        preferences = MainPreferencesWidget(Config())
        main_tab, anki_tab = preferences.widget(0), preferences.widget(1)
        assert main_tab is not None
        assert anki_tab is not None
        assert tuple(preferences.tabText(index) for index in range(preferences.count())) == scenario.tab_titles
        assert ANKI_KEYS == scenario.anki_keys
        assert all(getattr(preferences.widgets, key).parentWidget() == anki_tab for key in scenario.anki_keys)
        assert preferences.widgets.anki_shortcut.parentWidget() == main_tab
        assert (
            preferences.widgets.anki_connect_api_key.echoMode()
            == preferences.widgets.anki_connect_api_key.EchoMode.Password
        )


class AnkiFormLabelScenario(typing.NamedTuple):
    """One Anki widget and the label rendered for it in the form layout."""

    widget_name: str
    expected_label: str


ANKI_FORM_LABEL_SCENARIOS: dict[str, AnkiFormLabelScenario] = {
    "connect_url": AnkiFormLabelScenario(widget_name="anki_connect_url", expected_label="AnkiConnect URL"),
    "api_key": AnkiFormLabelScenario(widget_name="anki_connect_api_key", expected_label="AnkiConnect API key"),
    "image_field": AnkiFormLabelScenario(widget_name="anki_image_field", expected_label="Image field"),
    "field_separator": AnkiFormLabelScenario(widget_name="anki_field_separator", expected_label="Field separator"),
    "image_format": AnkiFormLabelScenario(widget_name="anki_image_format", expected_label="Image format"),
    "image_settings": AnkiFormLabelScenario(
        widget_name="anki_image_settings",
        expected_label="Image size and quality",
    ),
}


class TextNormalizationScenario(typing.NamedTuple):
    """An Anki text widget input and the config value copied from it."""

    widget_name: str
    entered_value: str
    config_name: str
    expected_value: str


TEXT_NORMALIZATION_SCENARIOS: dict[str, TextNormalizationScenario] = {
    "connect_url_strips": TextNormalizationScenario(
        widget_name="anki_connect_url",
        entered_value="  http://localhost:8765  ",
        config_name="anki_connect_url",
        expected_value="http://localhost:8765",
    ),
    "image_field_strips": TextNormalizationScenario(
        widget_name="anki_image_field",
        entered_value="  Image  ",
        config_name="anki_image_field",
        expected_value="Image",
    ),
    "api_key_preserves": TextNormalizationScenario(
        widget_name="anki_connect_api_key",
        entered_value="  key  ",
        config_name="anki_connect_api_key",
        expected_value="  key  ",
    ),
    "field_separator_preserves": TextNormalizationScenario(
        widget_name="anki_field_separator",
        entered_value="  <hr>  ",
        config_name="anki_field_separator",
        expected_value="  <hr>  ",
    ),
}


class TestAnkiFormWidgets:
    """Test labels and text normalization for Anki preferences widgets."""

    @pytest.mark.parametrize("scenario", ANKI_FORM_LABEL_SCENARIOS.values(), ids=ANKI_FORM_LABEL_SCENARIOS.keys())
    def test_form_labels(self, scenario: AnkiFormLabelScenario, qapp: QApplication) -> None:
        """Every Anki form widget is paired with the expected visible label."""
        preferences = MainPreferencesWidget(Config())
        anki_tab = preferences.widget(1)
        assert anki_tab is not None
        layout = anki_tab.layout()
        assert isinstance(layout, QFormLayout)
        label = layout.labelForField(getattr(preferences.widgets, scenario.widget_name))
        assert isinstance(label, QLabel)
        assert label.text() == scenario.expected_label

    @pytest.mark.parametrize("scenario", TEXT_NORMALIZATION_SCENARIOS.values(), ids=TEXT_NORMALIZATION_SCENARIOS.keys())
    def test_copy_text_normalization(self, scenario: TextNormalizationScenario, qapp: QApplication) -> None:
        """Copying preferences applies only the text normalization chosen by each widget type."""
        cfg = Config()
        preferences = MainPreferencesWidget(cfg)
        getattr(preferences.widgets, scenario.widget_name).setText(scenario.entered_value)
        preferences.copy_settings_to_cfg()
        assert getattr(cfg, scenario.config_name) == scenario.expected_value


def make_modified_config() -> Config:
    """Create a second fresh non-default configuration for round-trip coverage."""
    return Config(
        notification_duration_sec=30,
        max_history_size=500,
        bind_port=20000,
        force_cpu=True,
        show_help_bar=False,
        recover_missed_text=False,
        text_detection_resolution=1536,
        border_thickness=5,
        border_color="#AAAAAAAA",
        fill_color="#BBBBBBBB",
        outline_color="#CCCCCCCC",
        fill_brush_color="#DDDDDDDD",
        ocr_shortcut="Ctrl+O",
        ocr_page_shortcut="Ctrl+Shift+O",
        screenshot_shortcut="Ctrl+S",
        path_to_goldendict_executable="/usr/bin/goldendict",
        huggingface_model_name="test/model",
        huggingface_models=["test/model", "other/model"],
    )


ADDITIONAL_ROUND_TRIP_SCENARIOS: dict[str, ConfigScenario] = {
    "default_config": ConfigScenario(create=Config),
    "alternate_modified_config": ConfigScenario(create=make_modified_config),
}


class TestAdditionalRoundTripScenarios:
    """Preserve default and alternate modified-config round-trip cases."""

    @pytest.mark.parametrize(
        "scenario", ADDITIONAL_ROUND_TRIP_SCENARIOS.values(), ids=ADDITIONAL_ROUND_TRIP_SCENARIOS.keys()
    )
    def test_round_trip(self, scenario: ConfigScenario, qapp: QApplication) -> None:
        """Widgets preserve all fields for each additional config scenario."""
        source = scenario.create()
        target = Config()
        widgets = FormWidgetsBuilder(source).create_form_widgets()
        CopySettingsFromWidgetsToConfig(target, widgets).copy_settings_to_cfg()
        assert dataclasses.asdict(target) == dataclasses.asdict(source)


SAME_OBJECT_ROUND_TRIP_SCENARIOS: dict[str, ConfigScenario] = {
    "default_config": ConfigScenario(create=Config),
}


class TestSameObjectDefaultRoundTrip:
    """Verify copying default widgets back into their source Config does not mutate defaults."""

    @pytest.mark.parametrize(
        "scenario", SAME_OBJECT_ROUND_TRIP_SCENARIOS.values(), ids=SAME_OBJECT_ROUND_TRIP_SCENARIOS.keys()
    )
    def test_source_remains_default(self, scenario: ConfigScenario, qapp: QApplication) -> None:
        """A default Config remains equal to fresh defaults after serving as source and target."""
        source = scenario.create()
        widgets = FormWidgetsBuilder(source).create_form_widgets()
        CopySettingsFromWidgetsToConfig(source, widgets).copy_settings_to_cfg()
        assert dataclasses.asdict(source) == dataclasses.asdict(Config())


ROUNDING_SCENARIOS: dict[str, tuple[int, int]] = {"rounds_1000_to_1024": (1000, 1024)}


class TestTextDetectionResolutionRounding:
    """Test detector input-size normalization during widget-to-config copying."""

    @pytest.mark.parametrize("scenario", ROUNDING_SCENARIOS.values(), ids=ROUNDING_SCENARIOS.keys())
    def test_rounding(self, scenario: tuple[int, int], qapp: QApplication) -> None:
        """An off-stride detector size is rounded to the nearest stride."""
        initial, expected = scenario
        cfg = Config(text_detection_resolution=initial)
        widgets = FormWidgetsBuilder(cfg).create_form_widgets()
        CopySettingsFromWidgetsToConfig(cfg, widgets).copy_settings_to_cfg()
        assert cfg.text_detection_resolution == expected


SET_FROM_CFG_FIELDS: dict[str, str] = {
    "checkbox": "force_cpu",
    "spinbox": "notification_duration_sec",
    "color_picker": "border_color",
    "shortcut": "ocr_shortcut",
    "file_picker": "path_to_goldendict_executable",
    "enum_combo": "copy_to",
}


class TestSetFromCfgSupportedFields:
    """Test representative valid widget/value combinations."""

    @pytest.mark.parametrize("cfg_attr", SET_FROM_CFG_FIELDS.values(), ids=SET_FROM_CFG_FIELDS.keys())
    def test_set_from_cfg_succeeds(self, cfg_attr: str, qapp: QApplication) -> None:
        """Each representative config field can populate its corresponding widget."""
        cfg = Config()
        widgets = FormWidgetsBuilder(cfg).create_form_widgets()
        set_from_cfg(getattr(widgets, cfg_attr), getattr(cfg, cfg_attr))


def make_widget_population_config() -> Config:
    """Create the non-default source configuration for widget population assertions."""
    return Config(
        force_cpu=True,
        notification_duration_sec=45,
        border_thickness=10,
        ocr_shortcut="Ctrl+O",
        huggingface_model_name="test/model",
    )


WIDGET_POPULATION_SCENARIOS: dict[str, ConfigScenario] = {
    "selected_non_default_fields": ConfigScenario(create=make_widget_population_config),
}


class TestFormWidgetValuesPopulatesSelectedFields:
    """Test selected fields after populating an existing form."""

    @pytest.mark.parametrize("scenario", WIDGET_POPULATION_SCENARIOS.values(), ids=WIDGET_POPULATION_SCENARIOS.keys())
    def test_populated_values(self, scenario: ConfigScenario, qapp: QApplication) -> None:
        """Selected widgets reflect their supplied non-default config values."""
        cfg = scenario.create()
        widgets = FormWidgetsBuilder(Config()).create_form_widgets()
        FormWidgetValues(cfg, widgets).set_widget_values()
        assert widgets.force_cpu.isChecked() is True
        assert widgets.notification_duration_sec.value() == 45
        assert widgets.border_thickness.value() == 10
        assert widgets.ocr_shortcut.current_shortcut() == "Ctrl+O"
        assert widgets.huggingface_model.current_text() == "test/model"
