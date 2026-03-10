# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from PyQt6.QtWidgets import QSpinBox, QWidget


def ui_translate(key: str) -> str:
    """Convert a snake_case config key to a human-readable label."""
    return key.capitalize().replace("_", " ")


class SecondsSpinBox(QSpinBox):
    """A spin box pre-configured for selecting a duration in seconds."""

    min: int = 1
    max: int = 120
    suffix: str = "seconds"

    def __init__(self, initial_value: int, parent: QWidget | None = None) -> None:
        """Initialize the spin box with range, suffix, and initial value."""
        super().__init__(parent)
        self.setRange(self.min, self.max)
        if self.suffix:
            self.setSuffix(f" {self.suffix}")
        self.setValue(initial_value)


class HistorySizeSpinBox(SecondsSpinBox):
    """A spin box for selecting the maximum number of history items."""

    min: int = 1
    max: int = 1_000
    suffix: str = "items"


class BorderThicknessSpinBox(SecondsSpinBox):
    """A spin box for selecting the screenshot overlay border thickness in pixels."""

    min: int = 1
    max: int = 20
    suffix: str = "px"


class BindPortSpinBox(SecondsSpinBox):
    """A spin box for selecting the screenshot overlay border thickness in pixels."""

    min: int = 1025
    max: int = 32767
    suffix: str = ""
