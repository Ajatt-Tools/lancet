# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
import enum
import typing


@enum.unique
class AnkiImageFormat(enum.Enum):
    """Lossy image formats supported for Anki media attachments."""

    webp = "webp"
    avif = "avif"


class ImageParameters(typing.NamedTuple):
    """Maximum image dimensions and lossy encoding quality."""

    width: int
    height: int
    quality: int


class EncodedImage(typing.NamedTuple):
    """Encoded Anki media and the settings used to produce it."""

    data: bytes
    image_format: AnkiImageFormat
    settings: ImageParameters

    def size_kib(self) -> float:
        """Return the encoded media size as a floating-point KiB value."""
        return len(self.data) / 1024
