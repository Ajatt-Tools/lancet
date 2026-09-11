# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
import concurrent.futures
import functools
import typing

from loguru import logger
from PIL import Image
from zala.exceptions import ZalaException
from zala.main_window import UserSelectionResult
from zala.take_region import ZalaTakeScreenRegion
from zala.utils import ensure_cursor_restored

from lancet.anki.client import AnkiConnectClient
from lancet.anki.image import encode_image
from lancet.anki.image_types import EncodedImage, ImageParameters
from lancet.config import Config, make_preview_opts
from lancet.exceptions import PixmapConversionError
from lancet.model_utils.ocr_workflow import prepare_pillow_image
from lancet.notifications import NotifySend
from lancet.ocr.thread_op import LancetThreadOp


class AttachedImage(typing.NamedTuple):
    """The encoded media successfully attached to an Anki note."""

    note_id: int
    filename: str
    encoded: EncodedImage


class AnkiWorkflow:
    """Attach selected screen regions to the most recently added Anki note."""

    def __init__(
        self,
        cfg: Config,
        *,
        executor: concurrent.futures.ThreadPoolExecutor,
        notify: NotifySend,
        take: ZalaTakeScreenRegion,
        client: AnkiConnectClient | None = None,
    ) -> None:
        """Initialize the workflow with live configuration and its shared worker executor."""
        self._cfg = cfg
        self._executor = executor
        self._notify = notify
        self._take = take
        self._client = client or AnkiConnectClient(self._cfg)

    def screenshot_and_add_to_anki(self) -> None:
        """Resolve a stable target note before asking the user to select an image."""
        (
            LancetThreadOp[int](op=self._client.last_added_note_id, executor=self._executor)
            .success(self._start_anki_selection)
            .failure(self._notify_anki_failure)
            .run_in_background()
        )

    def _start_anki_selection(self, note_id: int) -> None:
        """Open the area selector after Anki preflight resolves a stable target note."""
        try:
            self._take.select_area(
                on_finish=functools.partial(self._attach_selection, note_id),
                opts=make_preview_opts(self._cfg),
            )
        except ZalaException as ex:
            self._notify_anki_failure(ex)

    def _notify_anki_failure(self, error: Exception) -> None:
        """Log and notify an Anki attachment failure reported by its workflow."""
        logger.warning(f"Anki attachment failed: {error}")
        self._notify.notify(f"Anki attachment failed: {error}")

    def _attach_selection(self, note_id: int, user_selection: UserSelectionResult) -> None:
        """Convert a selected Pixmap on the GUI thread, then attach it in a worker thread."""
        ensure_cursor_restored()
        try:
            image = prepare_pillow_image(user_selection)
        except PixmapConversionError as ex:
            self._notify_anki_failure(ex)
            return
        (
            LancetThreadOp[AttachedImage](
                op=functools.partial(self._attach_image, note_id, image),
                executor=self._executor,
            )
            .success(self._notify_success)
            .failure(self._notify_anki_failure)
            .run_in_background()
        )

    def _notify_success(self, result: AttachedImage) -> None:
        """Notify the user after an encoded image is attached to its target note."""
        self._notify.notify(
            f"Added {result.encoded.image_format.name} image to Anki note {result.note_id}: "
            f"{result.filename} ({result.encoded.size_kib():.2f} KiB)"
        )

    def _attach_image(self, note_id: int, image: Image.Image) -> AttachedImage:
        """Encode an image and attach it to the resolved target note."""
        encoded = encode_image(
            image,
            image_format=self._cfg.anki_image_format,
            settings=self._image_parameters(),
        )
        filename = self._client.attach_image(note_id, self._cfg.anki_image_field, encoded)
        return AttachedImage(filename=filename, note_id=note_id, encoded=encoded)

    def _image_parameters(self) -> ImageParameters:
        """Return current Anki image dimensions and quality as one non-swappable value."""
        return ImageParameters(
            width=self._cfg.anki_image_width,
            height=self._cfg.anki_image_height,
            quality=self._cfg.anki_image_quality,
        )
