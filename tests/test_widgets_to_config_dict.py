# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import functools
import operator
import typing
from collections.abc import Callable

import pytest
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QLineEdit,
    QPlainTextEdit,
    QSpinBox,
    QWidget,
)

from lancet.config import Config, OcrDestination
from lancet.gui.color_picker import ColorEditPicker
from lancet.gui.enum_select_combo import EnumSelectCombo
from lancet.gui.file_picker import LancetFilePicker
from lancet.gui.grab_key import ShortCutGrabButton
from lancet.gui.utils import DetectorInputSizeSpinBox
from lancet.gui.widgets_to_config_dict import (
    CfgValueTypes,
    get_from_widget,
    set_cfg_value,
    set_from_cfg,
)


def make_combo_box() -> QComboBox:
    """Return a combo box containing the test selections."""
    combo = QComboBox()
    combo.addItems(["first", "second"])
    return combo


def make_large_spin_box() -> QSpinBox:
    """Return an integer spin box that accepts the alternate test value."""
    widget = QSpinBox()
    widget.setRange(0, 10_000)
    return widget


def make_shortcut_button() -> ShortCutGrabButton:
    """Return an unassigned shortcut button."""
    return ShortCutGrabButton(initial_value="")


class WidgetMappingScenario(typing.NamedTuple):
    """A widget mapping and its normalized value."""

    factory: Callable[[], QWidget]
    value: CfgValueTypes
    expected: CfgValueTypes


WIDGET_MAPPING_SCENARIOS: dict[str, WidgetMappingScenario] = {
    "file_picker": WidgetMappingScenario(LancetFilePicker, " /opt/goldendict ", "/opt/goldendict"),
    "detector_size": WidgetMappingScenario(functools.partial(DetectorInputSizeSpinBox, initial_value=1024), 1050, 1024),
    "enum_combo": WidgetMappingScenario(
        functools.partial(EnumSelectCombo, initial_value=OcrDestination.goldendict),
        OcrDestination.clipboard,
        OcrDestination.clipboard,
    ),
    "double_spin": WidgetMappingScenario(QDoubleSpinBox, 12.5, 12.5),
    "spin": WidgetMappingScenario(QSpinBox, 42, 42),
    "color": WidgetMappingScenario(
        functools.partial(ColorEditPicker, initial_color="#FF000000"), "#aa112233", "#AA112233"
    ),
    "combo": WidgetMappingScenario(make_combo_box, "second", "second"),
    "line_edit": WidgetMappingScenario(QLineEdit, " value ", " value "),
    "checkbox": WidgetMappingScenario(QCheckBox, True, True),
    "shortcut": WidgetMappingScenario(
        functools.partial(ShortCutGrabButton, initial_value=""), " Ctrl+Shift+J ", "Ctrl+Shift+J"
    ),
    "plain_text": WidgetMappingScenario(QPlainTextEdit, "first\nsecond", "first\nsecond"),
    "alternate_spin_value": WidgetMappingScenario(make_large_spin_box, 123, 123),
    "alternate_detector_size": WidgetMappingScenario(DetectorInputSizeSpinBox, 1000, 1024),
    "uppercase_color": WidgetMappingScenario(
        functools.partial(ColorEditPicker, initial_color="#FF000000"), "#FF112233", "#FF112233"
    ),
    "alternate_line_edit": WidgetMappingScenario(QLineEdit, "plain text", "plain text"),
    "alternate_file_path": WidgetMappingScenario(LancetFilePicker, "  /usr/bin/goldendict  ", "/usr/bin/goldendict"),
    "alternate_shortcut": WidgetMappingScenario(make_shortcut_button, "Ctrl+O", "Ctrl+O"),
    "historical_plain_text_payload": WidgetMappingScenario(QPlainTextEdit, "plain\ntext", "plain\ntext"),
}


class TestWidgetMappings:
    """Test every supported widget-to-config mapping."""

    @pytest.mark.parametrize("scenario", WIDGET_MAPPING_SCENARIOS.values(), ids=WIDGET_MAPPING_SCENARIOS.keys())
    def test_round_trip(self, scenario: WidgetMappingScenario, qapp: QApplication) -> None:
        """Configuration values survive their supported widget mapping."""
        widget = scenario.factory()
        set_from_cfg(widget, scenario.value)
        assert get_from_widget(widget) == scenario.expected


class UnsupportedWidgetScenario(typing.NamedTuple):
    """An unsupported widget operation and expected message."""

    operation: typing.Literal["set", "get"]
    factory: Callable[[], QWidget]
    value: CfgValueTypes
    expected_message: str


UNSUPPORTED_WIDGET_SCENARIOS: dict[str, UnsupportedWidgetScenario] = {
    "set_wrong_value_type": UnsupportedWidgetScenario(
        "set", QLineEdit, 7, "Can't handle widget of type QLineEdit and value of type int"
    ),
    "set_unknown_widget": UnsupportedWidgetScenario(
        "set", QWidget, 7, "Can't handle widget of type QWidget and value of type int"
    ),
    "set_unknown_widget_with_string": UnsupportedWidgetScenario(
        "set", QWidget, "value", "Can't handle widget of type QWidget and value of type str"
    ),
    "set_bool_on_spin_box": UnsupportedWidgetScenario(
        "set", QSpinBox, True, "Can't handle widget of type QSpinBox and value of type bool"
    ),
    "set_bool_on_double_spin_box": UnsupportedWidgetScenario(
        "set", QDoubleSpinBox, True, "Can't handle widget of type QDoubleSpinBox and value of type bool"
    ),
    "get_unknown_widget": UnsupportedWidgetScenario(
        "get", QWidget, 0, "Don't know how to handle widget of type QWidget."
    ),
}


class TestUnsupportedWidgets:
    """Test public errors for unsupported widget mappings."""

    @pytest.mark.parametrize("scenario", UNSUPPORTED_WIDGET_SCENARIOS.values(), ids=UNSUPPORTED_WIDGET_SCENARIOS.keys())
    def test_raises(self, scenario: UnsupportedWidgetScenario, qapp: QApplication) -> None:
        """Unsupported mappings raise a descriptive ValueError."""
        widget = scenario.factory()
        with pytest.raises(ValueError) as exc_info:
            if scenario.operation == "set":
                set_from_cfg(widget, scenario.value)
            else:
                get_from_widget(widget)
        assert str(exc_info.value) == scenario.expected_message


class ConfigAssignmentScenario(typing.NamedTuple):
    """A runtime Config assignment and expected outcome."""

    key: str
    value: CfgValueTypes
    error_type: type[Exception] | None
    expected: object


class IntSubclass(int):
    """An int subclass used to verify legitimate subclasses remain accepted."""


CONFIG_ASSIGNMENT_SCENARIOS: dict[str, ConfigAssignmentScenario] = {
    "valid": ConfigAssignmentScenario("notification_duration_sec", 25, None, 25),
    "unknown_key": ConfigAssignmentScenario("missing", 1, AttributeError, "config has no attribute 'missing'"),
    "wrong_type": ConfigAssignmentScenario(
        "notification_duration_sec",
        "10",
        TypeError,
        "types differ in widget and config: <class 'int'> != <class 'str'>",
    ),
    "bool_for_int": ConfigAssignmentScenario(
        "notification_duration_sec",
        True,
        TypeError,
        "types differ in widget and config: <class 'int'> != <class 'bool'>",
    ),
    "alternate_matching_int": ConfigAssignmentScenario("notification_duration_sec", 42, None, 42),
    "matching_int_subclass": ConfigAssignmentScenario(
        "notification_duration_sec", IntSubclass(42), None, IntSubclass(42)
    ),
    "bool_for_bind_port": ConfigAssignmentScenario(
        "bind_port",
        True,
        TypeError,
        "types differ in widget and config: <class 'int'> != <class 'bool'>",
    ),
    "alternate_unknown_key": ConfigAssignmentScenario(
        "unknown", "value", AttributeError, "config has no attribute 'unknown'"
    ),
    "wrong_bool_field_type": ConfigAssignmentScenario(
        "force_cpu",
        "true",
        TypeError,
        "types differ in widget and config: <class 'bool'> != <class 'str'>",
    ),
}


class TestConfigAssignment:
    """Test checked runtime assignment to Config fields."""

    @pytest.mark.parametrize("scenario", CONFIG_ASSIGNMENT_SCENARIOS.values(), ids=CONFIG_ASSIGNMENT_SCENARIOS.keys())
    def test_assignment(self, scenario: ConfigAssignmentScenario) -> None:
        """Valid values are assigned and invalid values raise their public error."""
        cfg = Config()
        if scenario.error_type is None:
            set_cfg_value(cfg, scenario.key, scenario.value)
            assert operator.attrgetter(scenario.key)(cfg) == scenario.expected
            return
        with pytest.raises(scenario.error_type) as exc_info:
            set_cfg_value(cfg, scenario.key, scenario.value)
        assert str(exc_info.value) == scenario.expected
