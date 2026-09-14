# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
import io

from PIL import Image, features

from lancet.anki.image_types import AnkiImageFormat, EncodedImage, ImageParameters
from lancet.exceptions import AnkiImageEncodingError


def ensure_image_format_supported(image_format: AnkiImageFormat) -> None:
    """Raise when Pillow cannot encode the configured Anki image format."""
    # Official Pillow wheels support both codecs. Keep both choices visible and
    # fail explicitly for exceptional custom/source builds instead of hiding or
    # silently substituting the user's configured output format.
    if not features.check(image_format.value):
        raise AnkiImageEncodingError(f"Pillow does not support {image_format.value.upper()} image encoding")


def validate_image_parameters(settings: ImageParameters) -> None:
    """Raise when image dimensions or quality are outside their supported ranges."""
    if settings.width < 0 or settings.height < 0:
        raise AnkiImageEncodingError("Image dimensions cannot be negative")
    if not 0 <= settings.quality <= 100:
        raise AnkiImageEncodingError("Image quality must be between 0 and 100")


def resize_image(image: Image.Image, settings: ImageParameters) -> Image.Image:
    """Return an RGB copy constrained to maximum bounds without enlarging it."""
    result = image.convert("RGB")
    if settings.width or settings.height:
        result.thumbnail(
            (settings.width or result.width, settings.height or result.height),
            Image.Resampling.LANCZOS,
        )
    return result


def encode_image(
    image: Image.Image,
    *,
    image_format: AnkiImageFormat,
    settings: ImageParameters,
) -> EncodedImage:
    """Resize and encode an image in memory for Anki media storage."""
    validate_image_parameters(settings)
    ensure_image_format_supported(image_format)
    resized = resize_image(image, settings)
    output = io.BytesIO()
    try:
        resized.save(output, format=image_format.name.upper(), quality=settings.quality)
    except (OSError, ValueError) as ex:
        raise AnkiImageEncodingError(f"Could not encode {image_format.value.upper()} image: {ex}") from ex
    return EncodedImage(output.getvalue(), image_format, settings)
