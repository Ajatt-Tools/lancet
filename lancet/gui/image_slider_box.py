# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
import typing
from collections.abc import Iterable

from PyQt6.QtWidgets import QGridLayout, QLabel, QLayout, QWidget

from lancet.anki.image_types import ImageParameters
from lancet.consts import ANKI_IMAGE_MAX_DIMENSION
from lancet.gui.rich_slider import RichSlider


class Sliders(typing.NamedTuple):
    """The three controls comprising an image encoding configuration."""

    image_width: RichSlider
    image_height: RichSlider
    image_quality: RichSlider


def sliders_to_grid(sliders: Iterable[RichSlider]) -> QLayout:
    """Return a compact grid containing titles, sliders, spin boxes, and units."""
    grid = QGridLayout()
    slider: RichSlider
    for y_index, slider in enumerate(sliders):
        grid.addWidget(QLabel(slider.title), y_index, 0)
        for x_index, widget in enumerate(slider.widgets, start=1):
            grid.addWidget(widget, y_index, x_index)
    return grid


class ImageSliderBox(QWidget):
    """Composite widget for maximum image bounds and lossy-codec quality."""

    def __init__(
        self,
        parent: QWidget | None = None,
        max_width: int = ANKI_IMAGE_MAX_DIMENSION,
        max_height: int = ANKI_IMAGE_MAX_DIMENSION,
    ) -> None:
        """Create image width, height, and quality controls with zero-capable bounds."""
        super().__init__(parent=parent)
        self._sliders = Sliders(
            image_width=RichSlider("Width", "px", upper_limit=max_width),
            image_height=RichSlider("Height", "px", upper_limit=max_height),
            image_quality=RichSlider("Quality", "%", upper_limit=100, step=1),
        )
        self._setup_ui()
        self.set_tooltips()

    def _setup_ui(self) -> None:
        """Lay out the controls without adding form-row margins."""
        layout = sliders_to_grid(self._sliders)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

    def set_limits(self, width: int, height: int) -> None:
        """Set inclusive maximum bounds for image dimensions."""
        self._sliders.image_width.set_upper_limit(width)
        self._sliders.image_height.set_upper_limit(height)

    def values(self) -> ImageParameters:
        """Return the current width, height, and quality values."""
        return ImageParameters(
            width=self.image_width,
            height=self.image_height,
            quality=self.image_quality,
        )

    def set_values(self, *, width: int, height: int, quality: int) -> None:
        """Set all image encoding controls at once."""
        self.image_width = width
        self.image_height = height
        self.image_quality = quality

    @property
    def image_width(self) -> int:
        """Return the configured maximum image width, or zero when unconstrained."""
        return self._sliders.image_width.value

    @image_width.setter
    def image_width(self, value: int) -> None:
        """Set the configured maximum image width."""
        self._sliders.image_width.value = value

    @property
    def image_height(self) -> int:
        """Return the configured maximum image height, or zero when unconstrained."""
        return self._sliders.image_height.value

    @image_height.setter
    def image_height(self, value: int) -> None:
        """Set the configured maximum image height."""
        self._sliders.image_height.value = value

    @property
    def image_quality(self) -> int:
        """Return the configured lossy-image quality percentage."""
        return self._sliders.image_quality.value

    @image_quality.setter
    def image_quality(self, value: int) -> None:
        """Set the configured lossy-image quality percentage."""
        self._sliders.image_quality.value = value

    def set_tooltips(self) -> None:
        """Explain maximum-bound resize and compression behavior."""
        dimension_tooltip = (
            "Maximum image %s. Zero leaves this dimension unconstrained.\n"
            "Images preserve aspect ratio and are never enlarged."
        )
        quality_tooltip = "Compression quality from 0 to 100. Higher values produce larger, clearer images."
        self._sliders.image_width.set_tooltip(dimension_tooltip % "width")
        self._sliders.image_height.set_tooltip(dimension_tooltip % "height")
        self._sliders.image_quality.set_tooltip(quality_tooltip)
