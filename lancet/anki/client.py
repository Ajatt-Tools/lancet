# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
import base64
import contextlib
import datetime
import typing

import requests
from loguru import logger

from lancet.anki.client_types import (
    AnkiConnectParams,
    AnkiConnectRequest,
    AnkiConnectResult,
    DeleteMediaFileParams,
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
from lancet.config import Config
from lancet.consts import APP_NAME
from lancet.exceptions import AnkiConnectError, AnkiConnectUnavailableError

ANKI_CONNECT_VERSION: typing.Final[int] = 6
ANKI_CONNECT_TIMEOUT_SEC: typing.Final[int] = 10


def join_html_content(old_content: str, new_content: str, sep: str) -> str:
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
    """Synchronous client for AnkiConnect's local JSON HTTP API."""

    _cfg: Config

    def __init__(self, cfg: Config) -> None:
        """Configure the AnkiConnect endpoint and optional API key."""
        self._cfg = cfg

    def invoke(self, action: str, params: AnkiConnectParams) -> AnkiConnectResult:
        """Invoke one AnkiConnect action and return its validated envelope result."""
        payload: AnkiConnectRequest = {"action": action, "version": ANKI_CONNECT_VERSION, "params": params}
        if self._cfg.anki_connect_api_key:
            payload["key"] = self._cfg.anki_connect_api_key
        try:
            response = requests.post(self._cfg.anki_connect_url, json=payload, timeout=ANKI_CONNECT_TIMEOUT_SEC)
            response.raise_for_status()
        except requests.ConnectionError as ex:
            raise AnkiConnectUnavailableError(f"Could not reach AnkiConnect: {ex}") from ex
        except requests.RequestException as ex:
            raise AnkiConnectError(f"Could not reach AnkiConnect: {ex}") from ex
        # Response validation belongs to the parser so this client stays focused
        # on transport and composing Anki operations.
        return parse_anki_response(response)

    def last_added_note_id(self) -> int:
        """Return the greatest note ID matching Anki's added:1 search query."""
        params: FindNotesParams = {"query": "added:1"}
        note_ids = parse_note_ids(self.invoke("findNotes", params))
        if not note_ids:
            raise AnkiConnectError("No recently added Anki note was found")
        return max(note_ids)  # ids are timestamps, max() will return the newest id.

    def note_field(self, note_id: int, field_name: str) -> str:
        """Return a note field's current HTML value after validating its presence."""
        params: NotesInfoParams = {"notes": [note_id]}
        return parse_note_field(self.invoke("notesInfo", params), note_id=note_id, field_name=field_name)

    def store_media(self, filename: str, data: bytes) -> str:
        """Store base64 media and return Anki's resulting media filename."""
        params: StoreMediaFileParams = {
            "filename": filename,
            "data": base64.b64encode(data).decode("ascii"),
            "deleteExisting": False,
        }
        return parse_media_filename(self.invoke("storeMediaFile", params))

    def update_note_field(self, note_id: int, field_name: str, value: str) -> None:
        """Replace one existing note field with the supplied HTML value."""
        params: UpdateNoteFieldsParams = {"note": {"id": note_id, "fields": {field_name: value}}}
        self.invoke("updateNoteFields", params)

    def browse_note(self, note_id: int) -> None:
        """Open Anki Browse filtered to one note ID."""
        params: GuiBrowseParams = {"query": f"nid:{note_id}"}
        self.invoke("guiBrowse", params)

    def delete_media(self, filename: str) -> None:
        """Delete an uploaded Anki media file after a failed note update."""
        params: DeleteMediaFileParams = {"filename": filename}
        self.invoke("deleteMediaFile", params)

    def attach_image(self, note_id: int, field_name: str, image: EncodedImage) -> str:
        """Upload an image, append it to a note field, and reselect the updated note."""
        # Selecting an impossible note ID forces Anki's Browser editor to lose focus
        # and flush pending edits. This must happen before notesInfo. Reading first
        # could capture stale HTML and overwrite the newer content during our update.
        self.browse_note(0)

        previous_html = self.note_field(note_id, field_name)
        filename = self.store_media(make_image_filename(note_id, image.image_format.value), image.data)
        new_html = join_html_content(
            old_content=previous_html,
            new_content=f'<img src="{filename}">',
            sep=self._cfg.anki_field_separator,
        )
        try:
            self.update_note_field(note_id, field_name, new_html)
        except Exception as ex:
            # Delete media and re-raise.
            logger.error(f"failed to update note field: {ex}")
            # Preserve the update failure even when rollback cannot contact Anki.
            with contextlib.suppress(Exception):
                self.delete_media(filename)
            raise

        # Reselect the target only after the update so the Browser displays the
        # field contents containing the newly attached image.
        self.browse_note(note_id)
        return filename
