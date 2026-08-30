# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import dataclasses
import typing

import pytest
from PyQt6.QtWidgets import QApplication

from lancet.config import Config, OcrDestination
from lancet.gui.form_widgets import FormWidgets, FormWidgetsBuilder
from lancet.gui.preferences_widget import (
    SPECIAL_KEYS,
    CopySettingsFromWidgetsToConfig,
    FormWidgetValues,
    label_replace,
)
from lancet.gui.widgets_to_config_dict import set_from_cfg


class FieldParityScenario(typing.NamedTuple):
    """Exceptional form fields and the Config fields they represent."""

    special_widget_fields: frozenset[str]
    represented_config_fields: frozenset[str]


FIELD_PARITY_SCENARIOS: dict[str, FieldParityScenario] = {
    "huggingface_model": FieldParityScenario(
        special_widget_fields=frozenset({"huggingface_model"}),
        represented_config_fields=frozenset({"huggingface_model_name", "huggingface_models"}),
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


ROUND_TRIP_SCENARIOS: dict[str, Config] = {
    "non_default_values": Config(
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
        path_to_goldendict_executable="/opt/goldendict",
        border_thickness=7,
        border_color="#AA112233",
        fill_color="#BB223344",
        outline_color="#CC334455",
        fill_brush_color="#DD445566",
        bind_port=23456,
    )
}


class TestConfigFormRoundTrip:
    """Test complete Config-to-widget-to-Config conversion."""

    @pytest.mark.parametrize("source", ROUND_TRIP_SCENARIOS.values(), ids=ROUND_TRIP_SCENARIOS.keys())
    def test_round_trip(self, source: Config, qapp: QApplication) -> None:
        """All configuration fields survive conversion through form widgets."""
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
    "sec_suffix": LabelReplaceScenario("notification_duration_sec", "notification_duration"),
    "goldendict_prefix": LabelReplaceScenario("path_to_goldendict_executable", "goldendict_executable"),
    "passthrough_simple": LabelReplaceScenario("border_thickness", "border_thickness"),
    "passthrough_copy_to": LabelReplaceScenario("copy_to", "copy_to"),
    "passthrough_shortcut": LabelReplaceScenario("ocr_shortcut", "ocr_shortcut"),
}


class TestLabelReplace:
    """Test config-key mapping to display-label keys."""

    @pytest.mark.parametrize("scenario", LABEL_REPLACE_SCENARIOS.values(), ids=LABEL_REPLACE_SCENARIOS.keys())
    def test_replace(self, scenario: LabelReplaceScenario) -> None:
        """Each config key maps to its expected display key."""
        assert label_replace(scenario.cfg_key) == scenario.expected


MODIFIED_CONFIG = Config(
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


ADDITIONAL_ROUND_TRIP_SCENARIOS: dict[str, Config] = {
    "default_config": Config(),
    "alternate_modified_config": MODIFIED_CONFIG,
}


class TestAdditionalRoundTripScenarios:
    """Preserve default and alternate modified-config round-trip cases."""

    @pytest.mark.parametrize(
        "source", ADDITIONAL_ROUND_TRIP_SCENARIOS.values(), ids=ADDITIONAL_ROUND_TRIP_SCENARIOS.keys()
    )
    def test_round_trip(self, source: Config, qapp: QApplication) -> None:
        """Widgets preserve all fields for each additional config scenario."""
        source = dataclasses.replace(source, huggingface_models=list(source.huggingface_models))
        target = Config()
        widgets = FormWidgetsBuilder(source).create_form_widgets()
        CopySettingsFromWidgetsToConfig(target, widgets).copy_settings_to_cfg()
        assert dataclasses.asdict(target) == dataclasses.asdict(source)


SAME_OBJECT_ROUND_TRIP_SCENARIOS: dict[str, Config] = {"default_config": Config()}


class TestSameObjectDefaultRoundTrip:
    """Verify copying default widgets back into their source Config does not mutate defaults."""

    @pytest.mark.parametrize(
        "source", SAME_OBJECT_ROUND_TRIP_SCENARIOS.values(), ids=SAME_OBJECT_ROUND_TRIP_SCENARIOS.keys()
    )
    def test_source_remains_default(self, source: Config, qapp: QApplication) -> None:
        """A default Config remains equal to fresh defaults after serving as source and target."""
        source = dataclasses.replace(source, huggingface_models=list(source.huggingface_models))
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


WIDGET_POPULATION_SCENARIOS: dict[str, Config] = {
    "selected_non_default_fields": Config(
        force_cpu=True,
        notification_duration_sec=45,
        border_thickness=10,
        ocr_shortcut="Ctrl+O",
        huggingface_model_name="test/model",
    )
}


class TestFormWidgetValuesPopulatesSelectedFields:
    """Test selected fields after populating an existing form."""

    @pytest.mark.parametrize("cfg", WIDGET_POPULATION_SCENARIOS.values(), ids=WIDGET_POPULATION_SCENARIOS.keys())
    def test_populated_values(self, cfg: Config, qapp: QApplication) -> None:
        """Selected widgets reflect their supplied non-default config values."""
        widgets = FormWidgetsBuilder(Config()).create_form_widgets()
        FormWidgetValues(cfg, widgets).set_widget_values()
        assert widgets.force_cpu.isChecked() is True
        assert widgets.notification_duration_sec.value() == 45
        assert widgets.border_thickness.value() == 10
        assert widgets.ocr_shortcut.current_shortcut() == "Ctrl+O"
        assert widgets.huggingface_model.current_text() == "test/model"
