# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import abc
import dataclasses
import pathlib
import typing

from PIL import Image

from lancet.exceptions import LancetException
from lancet.model_utils.base import LancetModel


def clamp[T: typing.SupportsInt | typing.SupportsFloat](min_val: T, val: T, max_val: T) -> T:
    """Clamp val to the range [min_val, max_val]."""
    return max(min_val, min(val, max_val))


class ComicTextDetectorException(LancetException):
    """Base exception for all comic text detector related errors."""

    pass


class ComicTextDetectorUnavailableError(ComicTextDetectorException):
    """Comic Text Detector model is still loading."""

    pass


class PointF(typing.NamedTuple):
    """A 2D point with float coordinates."""

    x: float
    y: float


class Quad(typing.NamedTuple):
    """A quadrilateral defined by four points."""

    p1: PointF
    p2: PointF
    p3: PointF
    p4: PointF

    @classmethod
    def from_nested(cls, points: list[list[float]]) -> typing.Self:
        """Create a Quad from a list of four [x, y] pairs, as returned by TextBlock.lines_array().tolist()."""
        return cls(*(PointF(*p) for p in points))


class Rect(typing.NamedTuple):
    """Bounding box defined by top-left and bottom-right corners."""

    x1: int
    y1: int
    x2: int
    y2: int

    @classmethod
    def new(cls, xyxy: typing.Sequence[typing.SupportsInt]) -> typing.Self:
        """Create a Rect from four integer-like values, converting numpy types to native int."""
        return cls(*map(int, xyxy))

    def has_area(self) -> bool:
        """Return True if the rectangle has positive width and height."""
        return self.x2 > self.x1 and self.y2 > self.y1

    def clamp(self, *, img_width: int, img_height: int) -> typing.Self:
        """
        Return a new Rect with coordinates clamped to [0, img_width) x [0, img_height).
        The caller should check has_area() afterward.
        """
        return type(self)(
            x1=clamp(0, self.x1, img_width),
            y1=clamp(0, self.y1, img_height),
            x2=clamp(0, self.x2, img_width),
            y2=clamp(0, self.y2, img_height),
        )


@dataclasses.dataclass(frozen=True)
class SpeechBubbleBlock:
    """A single detected text block within a speech bubble."""

    box: Rect
    box_image: Image.Image
    vertical: bool
    font_size: float
    lines_coords: list[Quad] = dataclasses.field(default_factory=list)
    lines: list[list[Image.Image]] = dataclasses.field(default_factory=list)


@dataclasses.dataclass(frozen=True)
class SpeechBubbleResult:
    """Result of detecting speech bubbles in an image."""

    version: str
    img_width: int
    img_height: int
    blocks: list[SpeechBubbleBlock] = dataclasses.field(default_factory=list)


class ComicTextDetectorBase(LancetModel):
    """Abstract base class defining the interface for comic text detector implementations."""

    @property
    @abc.abstractmethod
    def force_cpu(self) -> bool:
        """Return whether the model was loaded with CPU forced."""
        raise NotImplementedError

    @abc.abstractmethod
    def get_speech_bubbles(
        self,
        img_or_path: pathlib.Path | Image.Image,
        *,
        include_lines: bool = False,
        keep_undetected_mask: bool = True,
    ) -> SpeechBubbleResult:
        """
        Detect speech bubbles in the given image or image file path.
        Do not include lines by default because they are not used by Lancet.
        """
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def detector_input_size(self) -> int:
        """Return the input resolution used by the text detector."""
        raise NotImplementedError
