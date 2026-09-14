# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
from collections.abc import Mapping, Sequence

import requests

from lancet.anki.client_types import AnkiConnectResult
from lancet.exceptions import AnkiConnectError


def validate_result_error(result: AnkiConnectResult, error: object) -> AnkiConnectResult:
    """Return result for a null error, or raise a normalized AnkiConnectError."""
    # Keep error as object until matching because decoded JSON is untrusted.
    # A str | None annotation would let beartype reject malformed values before
    # this boundary can convert them into the public AnkiConnectError contract.
    match error:
        case str():  # Valid error
            raise AnkiConnectError(error)
        case None:  # No error
            return result
        case _:  # Invalid error.
            raise AnkiConnectError("AnkiConnect response has an invalid error field")


def parse_response_envelope(data: object) -> AnkiConnectResult:
    """Validate AnkiConnect's common result/error envelope and return its result."""
    if not isinstance(data, Mapping):
        raise AnkiConnectError("AnkiConnect response is not a JSON object")
    try:
        result, error = data["result"], data["error"]
    except KeyError as ex:
        raise AnkiConnectError("AnkiConnect response is missing result or error") from ex
    return validate_result_error(result, error)


def parse_anki_response(response: requests.Response) -> AnkiConnectResult:
    """Decode and validate an AnkiConnect response envelope."""
    try:
        data = response.json()
    except ValueError as ex:
        raise AnkiConnectError(f"AnkiConnect returned invalid JSON: {ex}") from ex
    return parse_response_envelope(data)


def parse_note_ids(result: AnkiConnectResult) -> Sequence[int]:
    """Validate a findNotes or guiBrowse result as strict integer IDs."""
    # bool subclasses int, but true/false can never be valid Anki note IDs.
    if not isinstance(result, list) or any(type(item) is not int for item in result):
        raise AnkiConnectError("AnkiConnect returned an invalid list of IDs")
    return result


def parse_media_filename(result: AnkiConnectResult) -> str:
    """Validate a storeMediaFile result as a filename string."""
    if not (isinstance(result, str) and result):
        raise AnkiConnectError("AnkiConnect returned an invalid media filename")
    return result


def parse_note_field(result: AnkiConnectResult, *, note_id: int, field_name: str) -> str:
    """Validate notesInfo and return the requested field value."""
    if not isinstance(result, list) or len(result) != 1:
        raise AnkiConnectError(f"Anki note {note_id} was not found")
    note_info = result[0]
    if not isinstance(note_info, dict) or not isinstance(fields := note_info.get("fields"), dict):
        raise AnkiConnectError("AnkiConnect returned invalid note information")
    # Result is a list of dicts, each dict is a note with "fields" and other info.
    # https://git.sr.ht/~foosoft/anki-connect/tree/master/item/README.md#codenotesinfocode
    if field_name not in fields:
        raise AnkiConnectError(f"Anki note does not have an {field_name!r} field")
    field = fields[field_name]
    # A field has "value" and "order".
    if not isinstance(field, dict) or not isinstance(value := field.get("value"), str):
        raise AnkiConnectError(f"AnkiConnect returned an invalid value for field {field_name!r}")
    return value
