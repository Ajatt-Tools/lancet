# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from PyQt6.QtWidgets import QSpinBox, QWidget


def ui_translate(key: str) -> str:
    """Convert a snake_case config key to a human-readable label."""
    return key.capitalize().replace("_", " ").replace("cpu", "CPU").replace("Ocr", "OCR")


class SecondsSpinBox(QSpinBox):
    """A spin box pre-configured for selecting a duration in seconds."""

    _min: int = 1
    _max: int = 120
    _suffix: str = "seconds"

    def __init__(self, initial_value: int, parent: QWidget | None = None) -> None:
        """Initialize the spin box with range, suffix, and initial value."""
        super().__init__(parent)
        self.setRange(self._min, self._max)
        if self._suffix:
            self.setSuffix(f" {self._suffix}")
        self.setValue(initial_value)


class HistorySizeSpinBox(SecondsSpinBox):
    """A spin box for selecting the maximum number of history items."""

    _min: int = 1
    _max: int = 1_000
    _suffix: str = "items"


class BorderThicknessSpinBox(SecondsSpinBox):
    """A spin box for selecting the screenshot overlay border thickness in pixels."""

    _min: int = 1
    _max: int = 20
    _suffix: str = "px"


class BindPortSpinBox(SecondsSpinBox):
    """A spin box for selecting the screenshot overlay border thickness in pixels."""

    _min: int = 1025
    _max: int = 32767
    _suffix: str = ""


class DetectorInputSizeSpinBox(SecondsSpinBox):
    """Spin box for selecting the text detector input resolution."""

    _min: int = 512
    _max: int = 2048
    _suffix: str = "px"

    def __init__(self, initial_value: int = 1024, parent: QWidget | None = None) -> None:
        super().__init__(initial_value, parent)
        self.setSingleStep(64)
