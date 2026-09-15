# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
import concurrent.futures
import functools
import typing
from collections.abc import Callable

from loguru import logger
from PIL import Image
from zala.config import ScreenshotPreviewOpts
from zala.exceptions import ZalaException
from zala.main_window import UserSelectionResult
from zala.take_region import ZalaTakeScreenRegion
from zala.utils import ensure_cursor_restored

from lancet.anki.client import AnkiConnectClient, AnkiConnectClientFactory
from lancet.anki.image import encode_image
from lancet.anki.image_types import AnkiImageFormat, EncodedImage, ImageParameters
from lancet.config import Config
from lancet.exceptions import (
    AnkiAttachmentCanceledError,
    AnkiConnectUnavailableError,
    PixmapConversionError,
)
from lancet.gui.open_dialogs import OpenDialogs
from lancet.gui.preview_options import make_preview_opts
from lancet.model_utils.ocr_workflow import prepare_pillow_image
from lancet.notifications import NotifySend
from lancet.ocr.thread_op import LancetThreadOp


class AttachedImage(typing.NamedTuple):
    """The encoded media successfully attached to an Anki note."""

    note_id: int
    filename: str
    encoded: EncodedImage


class AnkiAttachmentJob:
    """Run one screenshot-to-Anki operation from preflight through delivery."""

    _on_failure: Callable[[Exception], None] | None
    _on_success: Callable[[AttachedImage], None] | None

    def __init__(
        self,
        *,
        client: AnkiConnectClient,
        executor: concurrent.futures.ThreadPoolExecutor,
        take: ZalaTakeScreenRegion,
        open_dialogs: OpenDialogs,
        preview_opts: ScreenshotPreviewOpts,
        image_format: AnkiImageFormat,
        image_parameters: ImageParameters,
    ) -> None:
        """Store immutable operation state and shared UI services."""
        self._client = client
        self._executor = executor
        self._take = take
        self._open_dialogs = open_dialogs
        self._preview_opts = preview_opts
        self._image_format = image_format
        self._image_parameters = image_parameters
        # callbacks
        self._on_success = None
        self._on_failure = None

    def success(self, success: Callable[[AttachedImage], None]) -> typing.Self:
        """Set the callback to invoke with the result when the operation succeeds."""
        self._on_success = success
        return self

    def failure(self, failure: Callable[[Exception], None]) -> typing.Self:
        """Set the callback to invoke with the exception when the operation fails."""
        self._on_failure = failure
        return self

    def start(self) -> None:
        """Resolve the target note before opening region selection."""
        if self._on_success is None:
            raise ValueError("success handler is not set")
        if self._on_failure is None:
            raise ValueError("failure handler is not set")
        (
            LancetThreadOp[int](op=self._client.last_added_note_id, executor=self._executor)
            .success(self._start_anki_selection)
            .failure(self._on_failure)
            .run_in_background()
        )

    def _start_anki_selection(self, note_id: int) -> None:
        """Open the area selector after Anki preflight resolves a stable target note."""
        assert self._on_failure is not None, "failure callback must be set"

        # Recheck after asynchronous preflight because the command dispatcher's
        # earlier dialog check may no longer reflect the current UI state.
        if self._open_dialogs.is_locked():
            logger.info("Anki preflight finished while a dialog was open; skipping selection")
            self._on_failure(AnkiAttachmentCanceledError("Anki attachment canceled because a dialog is open"))
            return

        # ZalaTakeScreenRegion owns screenshot-selection concurrency. Its lock
        # rejects overlapping select_area() calls and releases automatically
        # after selection finishes or initialization fails, so Lancet must not
        # add a second selection lock with a competing lifecycle.
        try:
            self._take.select_area(
                on_finish=functools.partial(self._attach_selection, note_id),
                opts=self._preview_opts,
            )
        except ZalaException as ex:
            self._on_failure(ex)

    def _attach_selection(self, note_id: int, user_selection: UserSelectionResult) -> None:
        """Convert a selected Pixmap on the GUI thread, then attach it in a worker thread."""
        assert self._on_failure is not None, "failure callback must be set"
        assert self._on_success is not None, "success callback must be set"

        ensure_cursor_restored()
        try:
            image = prepare_pillow_image(user_selection)
        except PixmapConversionError as ex:
            self._on_failure(ex)
            return
        (
            LancetThreadOp[AttachedImage](
                op=functools.partial(self._attach_image, note_id, image),
                executor=self._executor,
            )
            .success(self._on_success)
            .failure(self._on_failure)
            .run_in_background()
        )

    def _attach_image(self, note_id: int, image: Image.Image) -> AttachedImage:
        """Encode an image and attach it to the resolved target note."""
        encoded = encode_image(
            image,
            image_format=self._image_format,
            settings=self._image_parameters,
        )
        filename = self._client.attach_image(note_id, encoded)
        return AttachedImage(filename=filename, note_id=note_id, encoded=encoded)


class AnkiWorkflow:
    """Attach selected screen regions to the most recently added Anki note."""

    def __init__(
        self,
        cfg: Config,
        *,
        executor: concurrent.futures.ThreadPoolExecutor,
        notify: NotifySend,
        take: ZalaTakeScreenRegion,
        open_dialogs: OpenDialogs,
        client_factory: AnkiConnectClientFactory | None = None,
    ) -> None:
        """Initialize the workflow with live configuration and its shared worker executor."""
        self._cfg = cfg
        self._executor = executor
        self._notify = notify
        self._take = take
        self._open_dialogs = open_dialogs
        self._client_factory = client_factory or AnkiConnectClientFactory(self._cfg)

    def screenshot_and_add_to_anki(self) -> None:
        """Resolve a stable target note before asking the user to select an image."""
        job = AnkiAttachmentJob(
            client=self._client_factory.create(),
            executor=self._executor,
            take=self._take,
            open_dialogs=self._open_dialogs,
            preview_opts=make_preview_opts(self._cfg),
            image_format=self._cfg.anki_image_format,
            image_parameters=self._image_parameters(),
        )
        # ThreadOp and Zala retain the job through its bound callbacks for the
        # complete asynchronous lifecycle, so no workflow-owned job registry is needed.
        job.success(self._notify_success).failure(self._notify_anki_failure).start()

    def _notify_anki_failure(self, error: Exception) -> None:
        """Log and notify an Anki attachment failure reported by its workflow."""
        logger.warning(f"Anki attachment failed: {error}")
        # Keep transport diagnostics in logs, but make the expected missing-Anki
        # case immediately understandable in a short desktop notification.
        match error:
            case AnkiConnectUnavailableError() | AnkiAttachmentCanceledError():
                self._notify.notify(error.what)
            case _:
                self._notify.notify(f"Anki attachment failed: {error}")

    def _notify_success(self, result: AttachedImage) -> None:
        """Notify the user after an encoded image is attached to its target note."""
        self._notify.notify(
            f"Added {result.encoded.image_format.name} image to Anki note {result.note_id}: "
            f"{result.filename} ({result.encoded.size_kib():.2f} KiB)"
        )

    def _image_parameters(self) -> ImageParameters:
        """Return current Anki image dimensions and quality as one non-swappable value."""
        return ImageParameters(
            width=self._cfg.anki_image_width,
            height=self._cfg.anki_image_height,
            quality=self._cfg.anki_image_quality,
        )
