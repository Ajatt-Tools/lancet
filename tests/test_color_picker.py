# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import typing

import pytest
from PyQt6.QtWidgets import QApplication

from lancet.gui.color_picker import DEFAULT_COLOR, ColorEditPicker


class ColorSignalScenario(typing.NamedTuple):
    """A color-edit operation and emitted value."""

    operation: typing.Literal["edit", "set_color"]
    value: str


COLOR_SIGNAL_SCENARIOS: dict[str, ColorSignalScenario] = {
    "text_change": ColorSignalScenario("edit", "#00FF00FF"),
    "set_color": ColorSignalScenario("set_color", "#0000FFFF"),
}


class InitialColorScenario(typing.NamedTuple):
    """An initial color and the normalized picker color."""

    initial: str
    expected: str


INITIAL_COLOR_SCENARIOS: dict[str, InitialColorScenario] = {
    "valid_color": InitialColorScenario("#FF0000FF", "#FF0000FF"),
    "empty_falls_back_to_default": InitialColorScenario("", DEFAULT_COLOR),
}


class TestColorEditPickerSignal:
    """Test that ColorEditPicker emits color_changed when the text changes."""

    @pytest.mark.parametrize("scenario", COLOR_SIGNAL_SCENARIOS.values(), ids=COLOR_SIGNAL_SCENARIOS.keys())
    def test_signal_emitted(self, scenario: ColorSignalScenario, qapp: QApplication) -> None:
        """Direct edits and set_color both emit color_changed."""
        picker = ColorEditPicker(initial_color="#FF0000FF")
        received: list[str] = []
        picker.color_changed.connect(received.append)

        if scenario.operation == "edit":
            picker._edit.setText(scenario.value)
        else:
            picker.set_color(scenario.value)

        assert received == [scenario.value]

    @pytest.mark.parametrize("scenario", INITIAL_COLOR_SCENARIOS.values(), ids=INITIAL_COLOR_SCENARIOS.keys())
    def test_initial_color(self, scenario: InitialColorScenario, qapp: QApplication) -> None:
        """The picker initializes with the provided color or the default."""
        picker = ColorEditPicker(initial_color=scenario.initial)
        assert picker.color_hex() == scenario.expected.upper()
