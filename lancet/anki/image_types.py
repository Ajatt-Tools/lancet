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
