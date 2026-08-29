# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import pytest
from PyQt6.QtWidgets import QApplication

from lancet.gui.color_picker import DEFAULT_COLOR, ColorEditPicker


class TestColorEditPickerSignal:
    """Test that ColorEditPicker emits color_changed when the text changes."""

    def test_signal_emitted_on_text_change(self, qapp: QApplication) -> None:
        """Editing the text field emits color_changed with the new text."""
        picker = ColorEditPicker(initial_color="#FF0000FF")
        received: list[str] = []
        picker.color_changed.connect(lambda text: received.append(text))

        picker._edit.setText("#00FF00FF")

        assert received == ["#00FF00FF"]

    def test_signal_emitted_on_set_color(self, qapp: QApplication) -> None:
        """set_color writes into the edit, which emits color_changed."""
        picker = ColorEditPicker(initial_color="#FF0000FF")
        received: list[str] = []
        picker.color_changed.connect(lambda text: received.append(text))

        picker.set_color("#0000FFFF")

        assert received == ["#0000FFFF"]

    @pytest.mark.parametrize(
        "initial,expected",
        [
            ("#FF0000FF", "#FF0000FF"),
            ("", DEFAULT_COLOR),
        ],
        ids=["valid_color", "empty_falls_back_to_default"],
    )
    def test_initial_color(self, initial: str, expected: str, qapp: QApplication) -> None:
        """The picker initializes with the provided color or the default."""
        picker = ColorEditPicker(initial_color=initial)
        assert picker.color_hex() == expected.upper()
