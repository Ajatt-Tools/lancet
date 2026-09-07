# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QSlider, QSpinBox
from zala.utils import qconnect


class RichSlider:
    """Keep a horizontal slider and a spin box synchronized."""

    SLIDER_STEP = 5

    def __init__(
        self, title: str, unit: str = "px", lower_limit: int = 0, upper_limit: int = 100, step: int = SLIDER_STEP
    ) -> None:
        """Create synchronized controls with a label and configured range."""
        self.title = title
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.spinbox = QSpinBox()
        self.unit_label = QLabel(unit)
        qconnect(self.slider.valueChanged, self.spinbox.setValue)
        qconnect(self.spinbox.valueChanged, self.slider.setValue)
        self.set_range(lower_limit, upper_limit)
        self._set_step(step)

    def set_range(self, start: int, stop: int) -> None:
        """Set the inclusive range for both controls."""
        self.slider.setRange(start, stop)
        self.spinbox.setRange(start, stop)

    def set_upper_limit(self, limit: int) -> None:
        """Set the maximum value while retaining the zero lower bound."""
        self.set_range(0, limit)

    def set_tooltip(self, tooltip: str) -> None:
        """Set the same tooltip on every visible control."""
        self.slider.setToolTip(tooltip)
        self.spinbox.setToolTip(tooltip)
        self.unit_label.setToolTip(tooltip)

    @property
    def widgets(self) -> tuple[QSlider, QSpinBox, QLabel]:
        """Return widgets in layout order."""
        return self.slider, self.spinbox, self.unit_label

    @property
    def value(self) -> int:
        """Return the current shared value."""
        return self.slider.value()

    @value.setter
    def value(self, value: int) -> None:
        """Set the current value in both synchronized controls."""
        self.slider.setValue(value)
        self.spinbox.setValue(value)

    def _set_step(self, step: int) -> None:
        """Set keyboard and spin-box increment sizes."""
        self.slider.setSingleStep(step)
        self.spinbox.setSingleStep(step)
