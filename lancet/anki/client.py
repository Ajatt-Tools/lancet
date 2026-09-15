# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
import base64
import datetime
import threading
import typing
from collections.abc import Generator
from contextlib import contextmanager

import requests
from loguru import logger

from lancet.anki.client_types import (
    AnkiConnectParams,
    AnkiConnectRequest,
    AnkiConnectResult,
    FindNotesParams,
    GuiBrowseParams,
    NotesInfoParams,
    StoreMediaFileParams,
    UpdateNoteFieldsParams,
)
from lancet.anki.image_types import EncodedImage
from lancet.anki.response_parser import (
    parse_anki_response,
    parse_media_filename,
    parse_note_field,
    parse_note_ids,
)
from lancet.anki.settings import AnkiConnectSettings
from lancet.config import Config
from lancet.consts import APP_NAME
from lancet.exceptions import (
    AnkiAttachmentInProgressError,
    AnkiConnectError,
    AnkiConnectUnavailableError,
)

ANKI_CONNECT_VERSION: typing.Final[int] = 6
ANKI_CONNECT_TIMEOUT_SEC: typing.Final[int] = 10


def join_html_content(old_content: str, new_content: str, *, sep: str) -> str:
    """Join non-empty HTML fragments without modifying their contents."""
    # Whitespace-only fragments are semantically empty, so they should not
    # introduce a separator before or after the actual field content.
    if not old_content.strip():
        return new_content
    if not new_content.strip():
        return old_content

    # Strip only for the emptiness checks above. Whitespace can be meaningful
    # inside HTML such as <pre>, so preserve both original fragments exactly.
    return f"{old_content}{sep}{new_content}"


def make_image_filename(note_id: int, container: str) -> str:
    """Build a timestamped media filename unique to the target note and image container."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    return f"{APP_NAME.lower()}_{note_id}_{timestamp}.{container}"


class AnkiConnectClient:
    """Synchronous client for one immutable AnkiConnect target."""

    _opts: AnkiConnectSettings
    _attachment_lock: threading.Lock

    def __init__(self, settings: AnkiConnectSettings, *, attachment_lock: threading.Lock) -> None:
        """Configure one operation target and its shared attachment transaction lock."""
        self._opts = settings
        self._attachment_lock = attachment_lock

    def invoke(self, action: str, params: AnkiConnectParams) -> AnkiConnectResult:
        """Invoke one AnkiConnect action and return its validated envelope result."""
        payload: AnkiConnectRequest = {"action": action, "version": ANKI_CONNECT_VERSION, "params": params}
        if self._opts.api_key:
            payload["key"] = self._opts.api_key
        try:
            response = requests.post(
                self._opts.url,
                json=payload,
                timeout=ANKI_CONNECT_TIMEOUT_SEC,
                allow_redirects=False,
            )
            response.raise_for_status()
        except requests.ConnectionError as ex:
            raise AnkiConnectUnavailableError(f"Could not reach AnkiConnect: {ex}") from ex
        except requests.RequestException as ex:
            raise AnkiConnectError(f"Could not reach AnkiConnect: {ex}") from ex
        if response.is_redirect:
            raise AnkiConnectError("AnkiConnect endpoint returned an HTTP redirect")
        # Response validation belongs to the parser so this client stays focused
        # on transport and composing Anki operations.
        return parse_anki_response(response)

    def last_added_note_id(self) -> int:
        """Return the greatest note ID matching Anki's added:1 search query."""
        params: FindNotesParams = {"query": "added:1"}
        note_ids = parse_note_ids(self.invoke("findNotes", params))
        if not note_ids:
            raise AnkiConnectError("No recently added Anki note was found")
        return max(note_ids)  # Note IDs are timestamps, so max() returns the newest note id.

    def note_field(self, note_id: int) -> str:
        """Return the configured note field's current HTML value after validation."""
        params: NotesInfoParams = {"notes": [note_id]}
        return parse_note_field(
            self.invoke("notesInfo", params),
            note_id=note_id,
            field_name=self._opts.field_name,
        )

    def store_media(self, filename: str, data: bytes) -> str:
        """Store base64 media and return Anki's resulting media filename."""
        params: StoreMediaFileParams = {
            "filename": filename,
            "data": base64.b64encode(data).decode("ascii"),
            "deleteExisting": False,
        }
        return parse_media_filename(self.invoke("storeMediaFile", params))

    def update_note_field(self, note_id: int, value: str) -> None:
        """Replace the configured note field with the supplied HTML value."""
        params: UpdateNoteFieldsParams = {"note": {"id": note_id, "fields": {self._opts.field_name: value}}}
        self.invoke("updateNoteFields", params)

    def browse_note(self, note_id: int) -> None:
        """Open Anki Browse filtered to one note ID."""
        params: GuiBrowseParams = {"query": f"nid:{note_id}"}
        self.invoke("guiBrowse", params)

    def attach_image(self, note_id: int, image: EncodedImage) -> str:
        """Serialize and perform one complete Anki field attachment transaction."""
        with self._exclusive_attachment():
            return self._attach_image(note_id, image)

    @contextmanager
    def _exclusive_attachment(self) -> Generator[None]:
        """Own the attachment transaction or reject concurrent Lancet updates."""
        if not self._attachment_lock.acquire(blocking=False):
            raise AnkiAttachmentInProgressError("Another Anki attachment is already in progress")
        try:
            yield
        finally:
            self._attachment_lock.release()

    def _attach_image(self, note_id: int, image: EncodedImage) -> str:
        """Upload one image, append it to a note field, and reselect the updated note."""
        # Selecting an impossible note ID asks Anki Browser to flush pending edits
        # before notesInfo. AnkiConnect does not expose a synchronous save barrier,
        # so users should finish active Browser edits before attaching an image.
        self.browse_note(0)

        previous_html = self.note_field(note_id)
        filename = self.store_media(make_image_filename(note_id, image.image_format.value), image.data)
        new_html = join_html_content(
            old_content=previous_html,
            new_content=f'<img src="{filename}">',
            sep=self._opts.field_separator,
        )

        # A transport failure cannot prove whether Anki committed the update.
        # Keep uploaded media intact because deleting it could break a note that now references it.
        # Anki's Check Media removes true orphans safely.
        self.update_note_field(note_id, new_html)

        # The attachment is committed even if this cosmetic Browser refresh fails.
        try:
            self.browse_note(note_id)
        except AnkiConnectError as ex:
            logger.warning(f"Anki attachment succeeded but Browser refresh failed: {ex}")
        return filename


class AnkiConnectClientFactory:
    """Create operation-specific clients sharing one attachment transaction lock."""

    def __init__(self, cfg: Config) -> None:
        """Store live configuration and initialize shared attachment ownership."""
        self._cfg = cfg
        self._attachment_lock = threading.Lock()

    def create(self) -> AnkiConnectClient:
        """Create a client from the current immutable AnkiConnect settings."""
        return AnkiConnectClient(
            AnkiConnectSettings.from_config(self._cfg),
            attachment_lock=self._attachment_lock,
        )
