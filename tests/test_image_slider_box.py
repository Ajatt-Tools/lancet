# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Tests for Anki image dimension, quality, and synchronized slider controls."""

import enum
import typing

import pytest
from PyQt6.QtWidgets import (
    QApplication,
    QGridLayout,
    QLabel,
    QSlider,
    QSpinBox,
    QWidget,
)

from lancet.anki.image_types import ImageParameters
from lancet.gui.image_slider_box import ImageSliderBox
from lancet.gui.rich_slider import RichSliderWidgets


class ImageSliderScenario(typing.NamedTuple):
    """One initial or bulk-set ImageSliderBox state and expected parameters."""

    set_values: bool
    values: ImageParameters


IMAGE_SLIDER_SCENARIOS: dict[str, ImageSliderScenario] = {
    "constructor_defaults": ImageSliderScenario(
        set_values=False,
        values=ImageParameters(width=0, height=0, quality=0),
    ),
    "configured_values": ImageSliderScenario(
        set_values=True,
        values=ImageParameters(width=600, height=250, quality=33),
    ),
}


class LimitScenario(typing.NamedTuple):
    """Initial image parameters, dimension limits, and expected clamped values."""

    initial: ImageParameters
    max_width: int
    max_height: int
    expected: ImageParameters


LIMIT_SCENARIOS: dict[str, LimitScenario] = {
    "clamps_both_dimensions": LimitScenario(
        initial=ImageParameters(width=500, height=400, quality=33),
        max_width=300,
        max_height=200,
        expected=ImageParameters(width=300, height=200, quality=33),
    ),
    "zero_width_limit": LimitScenario(
        initial=ImageParameters(width=100, height=150, quality=33),
        max_width=0,
        max_height=100,
        expected=ImageParameters(width=0, height=100, quality=33),
    ),
    "in_range_values_remain": LimitScenario(
        initial=ImageParameters(width=100, height=100, quality=33),
        max_width=300,
        max_height=200,
        expected=ImageParameters(width=100, height=100, quality=33),
    ),
}


class SliderStepScenario(typing.NamedTuple):
    """One semantically named ImageSliderBox control and its expected step."""

    title: str
    expected_step: int


SLIDER_STEP_SCENARIOS: dict[str, SliderStepScenario] = {
    "width": SliderStepScenario(title="Width", expected_step=5),
    "height": SliderStepScenario(title="Height", expected_step=5),
    "quality": SliderStepScenario(title="Quality", expected_step=1),
}


class SynchronizationSource(enum.StrEnum):
    """The RichSlider control whose change begins one synchronization scenario."""

    slider = "slider"
    spinbox = "spinbox"


class SynchronizationScenario(typing.NamedTuple):
    """One control update and the shared value expected from both widgets."""

    title: str
    source: SynchronizationSource
    value: int


SYNCHRONIZATION_SCENARIOS: dict[str, SynchronizationScenario] = {
    "slider_to_spinbox": SynchronizationScenario(title="Width", source=SynchronizationSource.slider, value=35),
    "spinbox_to_slider": SynchronizationScenario(title="Width", source=SynchronizationSource.spinbox, value=60),
}


def grid_widget(layout: QGridLayout, row: int, column: int) -> QWidget:
    """Return the widget in one grid cell or raise if the tested layout is incomplete."""
    item = layout.itemAtPosition(row, column)
    if item is None or (widget := item.widget()) is None:
        raise AssertionError(f"Image slider grid has no widget at row {row}, column {column}")
    return widget


def slider_widgets_for_title(box: ImageSliderBox, title: str) -> RichSliderWidgets:
    """Locate one RichSlider's controls by its visible title rather than QObject order."""
    layout = box.layout()
    if not isinstance(layout, QGridLayout):
        raise AssertionError("ImageSliderBox must use a QGridLayout")
    for row in range(layout.rowCount()):
        if isinstance(label := grid_widget(layout, row, 0), QLabel) and label.text() == title:
            slider, spinbox, unit_label = (
                grid_widget(layout, row, 1),
                grid_widget(layout, row, 2),
                grid_widget(layout, row, 3),
            )
            if isinstance(slider, QSlider) and isinstance(spinbox, QSpinBox) and isinstance(unit_label, QLabel):
                return RichSliderWidgets(slider=slider, spinbox=spinbox, unit_label=unit_label)
    raise AssertionError(f"ImageSliderBox has no {title!r} control")


class TestImageSliderBox:
    """Test the composite image settings widget."""

    @pytest.mark.parametrize("scenario", IMAGE_SLIDER_SCENARIOS.values(), ids=IMAGE_SLIDER_SCENARIOS.keys())
    def test_values(self, scenario: ImageSliderScenario, qapp: QApplication) -> None:
        """Constructor defaults and bulk settings produce the expected shared parameters."""
        box = ImageSliderBox()
        if scenario.set_values:
            box.set_values(width=scenario.values.width, height=scenario.values.height, quality=scenario.values.quality)
        assert box.values() == scenario.values

    @pytest.mark.parametrize("scenario", LIMIT_SCENARIOS.values(), ids=LIMIT_SCENARIOS.keys())
    def test_limits(self, scenario: LimitScenario, qapp: QApplication) -> None:
        """Dimension limits clamp only values above their inclusive maximums."""
        box = ImageSliderBox()
        box.set_values(width=scenario.initial.width, height=scenario.initial.height, quality=scenario.initial.quality)
        box.set_limits(width=scenario.max_width, height=scenario.max_height)
        assert box.values() == scenario.expected

    @pytest.mark.parametrize("scenario", SLIDER_STEP_SCENARIOS.values(), ids=SLIDER_STEP_SCENARIOS.keys())
    def test_steps(self, scenario: SliderStepScenario, qapp: QApplication) -> None:
        """Both controls in each semantic row use the configured increment."""
        box = ImageSliderBox()
        widgets = slider_widgets_for_title(box, scenario.title)
        assert widgets.slider.singleStep() == scenario.expected_step
        assert widgets.spinbox.singleStep() == scenario.expected_step

    @pytest.mark.parametrize("scenario", SYNCHRONIZATION_SCENARIOS.values(), ids=SYNCHRONIZATION_SCENARIOS.keys())
    def test_controls_stay_synchronized(self, scenario: SynchronizationScenario, qapp: QApplication) -> None:
        """A change from either visible control updates its paired control to the same value."""
        box = ImageSliderBox()
        widgets = slider_widgets_for_title(box, scenario.title)
        match scenario.source:
            case SynchronizationSource.slider:
                widgets.slider.setValue(scenario.value)
            case SynchronizationSource.spinbox:
                widgets.spinbox.setValue(scenario.value)
        assert widgets.slider.value() == scenario.value
        assert widgets.spinbox.value() == scenario.value
