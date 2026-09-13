# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Tests for AnkiConnect transport and note operations."""

import datetime
import enum
import typing
from collections.abc import Sequence
from unittest.mock import Mock, call, create_autospec

import pytest
import requests

from lancet.anki.client import (
    ANKI_CONNECT_TIMEOUT_SEC,
    AnkiConnectClient,
    join_html_content,
    make_image_filename,
)
from lancet.anki.client_types import (
    AnkiConnectParams,
    AnkiConnectRequest,
    DeleteMediaFileParams,
    FindNotesParams,
    GuiBrowseParams,
    UpdateNoteFieldsParams,
)
from lancet.anki.image_types import AnkiImageFormat, EncodedImage, ImageParameters
from lancet.config import Config
from lancet.consts import DEFAULT_ANKICONNECT_URL
from lancet.exceptions import AnkiConnectError, AnkiConnectUnavailableError

NOTE_ID = 42
IMAGE_FIELD = "Image"
IMAGE_DATA = b"image"
IMAGE_FILENAME = "lancet_42_2026-09-12-12-30-45.webp"
UPDATE_ERROR_MESSAGE = "update failed"


class RequestScenario(typing.NamedTuple):
    """An optional API key expected by an AnkiConnect request."""

    api_key: str


REQUEST_SCENARIOS: dict[str, RequestScenario] = {
    "with_api_key": RequestScenario(api_key="key"),
    "without_api_key": RequestScenario(api_key=""),
}


class RequestFailureScenario(typing.NamedTuple):
    """A request failure and the public exception type expected from the client."""

    error_type: type[requests.RequestException]
    error_message: str
    expected_error_type: type[AnkiConnectError]


REQUEST_FAILURE_SCENARIOS: dict[str, RequestFailureScenario] = {
    "connection_error": RequestFailureScenario(
        error_type=requests.ConnectionError,
        error_message="connection refused",
        expected_error_type=AnkiConnectUnavailableError,
    ),
    "timeout": RequestFailureScenario(
        error_type=requests.Timeout,
        error_message="request timed out",
        expected_error_type=AnkiConnectError,
    ),
}


class NoteSelectionScenario(typing.NamedTuple):
    """Recent note IDs and the expected selected ID or public error message."""

    note_ids: Sequence[int]
    expected_note_id: int | None
    expected_error_message: str


NOTE_SELECTION_SCENARIOS: dict[str, NoteSelectionScenario] = {
    "greatest_id": NoteSelectionScenario(note_ids=(7, 19, 11), expected_note_id=19, expected_error_message=""),
    "no_recent_notes": NoteSelectionScenario(
        note_ids=(), expected_note_id=None, expected_error_message="No recently added Anki note was found"
    ),
}


class SideEffectOperation(enum.StrEnum):
    """Side-effect-only AnkiConnect operations covered by the client tests."""

    update_note_field = "updateNoteFields"
    browse_note = "guiBrowse"
    delete_media = "deleteMediaFile"


class SideEffectScenario(typing.NamedTuple):
    """A side-effect-only client operation and its expected AnkiConnect action."""

    operation: SideEffectOperation


SIDE_EFFECT_SCENARIOS: dict[str, SideEffectScenario] = {
    "update_note_field": SideEffectScenario(operation=SideEffectOperation.update_note_field),
    "browse_note": SideEffectScenario(operation=SideEffectOperation.browse_note),
    "delete_media": SideEffectScenario(operation=SideEffectOperation.delete_media),
}


class AttachmentScenario(typing.NamedTuple):
    """A separator and the expected HTML after attaching one uploaded image."""

    separator: str
    expected_html: str


ATTACHMENT_SCENARIOS: dict[str, AttachmentScenario] = {
    "default_break": AttachmentScenario("<br>", '<p>existing</p><br><img src="lancet_actual.webp">'),
    "custom_rule": AttachmentScenario("<hr>", '<p>existing</p><hr><img src="lancet_actual.webp">'),
    "empty_separator": AttachmentScenario("", '<p>existing</p><img src="lancet_actual.webp">'),
}


class CleanupScenario(typing.NamedTuple):
    """Whether failed media cleanup also raises after the note update fails."""

    cleanup_error_type: type[Exception] | None


CLEANUP_SCENARIOS: dict[str, CleanupScenario] = {
    "cleanup_succeeds": CleanupScenario(cleanup_error_type=None),
    "cleanup_fails": CleanupScenario(cleanup_error_type=AnkiConnectError),
}


class FilenameScenario(typing.NamedTuple):
    """A note ID and image container used to generate a media filename."""

    note_id: int
    container: str
    expected_filename: str


FILENAME_SCENARIOS: dict[str, FilenameScenario] = {
    "webp": FilenameScenario(note_id=NOTE_ID, container="webp", expected_filename=IMAGE_FILENAME),
}


class NoteFieldScenario(typing.NamedTuple):
    """A current note field value returned by the notesInfo operation."""

    current_value: str


NOTE_FIELD_SCENARIOS: dict[str, NoteFieldScenario] = {
    "existing_image": NoteFieldScenario(current_value='<img src="existing.webp">'),
}


class StoreMediaScenario(typing.NamedTuple):
    """Media input and the filename AnkiConnect returns after storing it."""

    filename: str
    returned_filename: str


STORE_MEDIA_SCENARIOS: dict[str, StoreMediaScenario] = {
    "webp": StoreMediaScenario(filename=IMAGE_FILENAME, returned_filename="anki-assigned.webp"),
}


class AttachmentSetup(typing.NamedTuple):
    """An Anki client, ordered operation recorder, and image for attachment tests."""

    client: AnkiConnectClient
    operations: "AttachmentOperationRecorder"
    image: EncodedImage
    filename_factory: Mock


class AttachmentOperation(enum.StrEnum):
    """Client operations whose ordering matters when attaching one image."""

    browse_note = "browse_note"
    note_field = "note_field"
    store_media = "store_media"
    update_note_field = "update_note_field"


class AttachmentOperationCall(typing.NamedTuple):
    """One Anki client operation performed while attaching an image."""

    name: AttachmentOperation
    args: Sequence[int | str | bytes]


class AttachmentOperationRecorder:
    """Record the ordered client operations used by an image attachment test."""

    def __init__(self) -> None:
        """Initialize the empty attachment operation log."""
        self._calls: list[AttachmentOperationCall] = []

    @property
    def calls(self) -> tuple[AttachmentOperationCall, ...]:
        """Return an immutable snapshot of the recorded attachment operations."""
        return tuple(self._calls)

    def note_field(self, note_id: int, field_name: str) -> str:
        """Record a field lookup and return preexisting HTML content."""
        self._calls.append(AttachmentOperationCall(name=AttachmentOperation.note_field, args=(note_id, field_name)))
        return "<p>existing</p>"

    def store_media(self, filename: str, data: bytes) -> str:
        """Record media storage and return the filename assigned by Anki."""
        self._calls.append(AttachmentOperationCall(name=AttachmentOperation.store_media, args=(filename, data)))
        return "lancet_actual.webp"

    def browse_note(self, note_id: int) -> None:
        """Record opening Anki Browse for one note ID."""
        self._calls.append(AttachmentOperationCall(name=AttachmentOperation.browse_note, args=(note_id,)))

    def update_note_field(self, note_id: int, field_name: str, value: str) -> None:
        """Record the final HTML update for one note field."""
        self._calls.append(
            AttachmentOperationCall(name=AttachmentOperation.update_note_field, args=(note_id, field_name, value))
        )


class FixedDateTime(datetime.datetime):
    """Return a stable timestamp when media filename tests call datetime.now()."""

    @classmethod
    def now(cls, tz: datetime.tzinfo | None = None) -> typing.Self:
        """Return the timestamp encoded in FILENAME_SCENARIOS."""
        return cls(2026, 9, 12, 12, 30, 45, tzinfo=tz)


def expected_request(api_key: str) -> AnkiConnectRequest:
    """Build the exact version-six findNotes payload for one configured API key."""
    params: FindNotesParams = {"query": "added:1"}
    payload: AnkiConnectRequest = {"action": "findNotes", "version": 6, "params": params}
    if api_key:
        payload["key"] = api_key
    return payload


def create_attachment_setup(scenario: AttachmentScenario, monkeypatch: pytest.MonkeyPatch) -> AttachmentSetup:
    """Create an attachment client whose collaborators report their ordered operations."""
    client = AnkiConnectClient(
        Config(anki_connect_url=DEFAULT_ANKICONNECT_URL, anki_field_separator=scenario.separator)
    )
    operations = AttachmentOperationRecorder()
    filename_factory = Mock(return_value="lancet_actual.webp")
    monkeypatch.setattr(client, "note_field", operations.note_field)
    monkeypatch.setattr(client, "store_media", operations.store_media)
    monkeypatch.setattr(client, "browse_note", operations.browse_note)
    monkeypatch.setattr(client, "update_note_field", operations.update_note_field)
    monkeypatch.setattr("lancet.anki.client.make_image_filename", filename_factory)
    return AttachmentSetup(
        client=client,
        operations=operations,
        image=EncodedImage(
            data=IMAGE_DATA,
            image_format=AnkiImageFormat.webp,
            settings=ImageParameters(width=0, height=250, quality=33),
        ),
        filename_factory=filename_factory,
    )


def invoke_side_effect(client: AnkiConnectClient, scenario: SideEffectScenario) -> None:
    """Invoke one action whose successful AnkiConnect result is intentionally unused."""
    match scenario.operation:
        case SideEffectOperation.update_note_field:
            client.update_note_field(NOTE_ID, IMAGE_FIELD, "<img>")
        case SideEffectOperation.browse_note:
            client.browse_note(NOTE_ID)
        case SideEffectOperation.delete_media:
            client.delete_media("image.avif")


def expected_side_effect_params(scenario: SideEffectScenario) -> AnkiConnectParams:
    """Build the exact request parameters for one side-effect operation."""
    match scenario.operation:
        case SideEffectOperation.update_note_field:
            update_params: UpdateNoteFieldsParams = {"note": {"id": NOTE_ID, "fields": {IMAGE_FIELD: "<img>"}}}
            return update_params
        case SideEffectOperation.browse_note:
            browse_params: GuiBrowseParams = {"query": f"nid:{NOTE_ID}"}
            return browse_params
        case SideEffectOperation.delete_media:
            delete_params: DeleteMediaFileParams = {"filename": "image.avif"}
            return delete_params


class TestAnkiConnectInvoke:
    """Test protocol payload construction and response validation."""

    @pytest.mark.parametrize("scenario", REQUEST_SCENARIOS.values(), ids=REQUEST_SCENARIOS.keys())
    def test_request_payload(self, scenario: RequestScenario, monkeypatch: pytest.MonkeyPatch) -> None:
        """Transport sends the configured endpoint, version-six payload, and timeout."""
        response = create_autospec(requests.Response, instance=True)
        response.json.return_value = {"result": [1], "error": None}
        post = Mock(return_value=response)
        monkeypatch.setattr("lancet.anki.client.requests.post", post)
        client = AnkiConnectClient(
            Config(anki_connect_url=DEFAULT_ANKICONNECT_URL, anki_connect_api_key=scenario.api_key)
        )
        assert client.invoke("findNotes", {"query": "added:1"}) == [1]
        assert post.call_args == call(
            DEFAULT_ANKICONNECT_URL,
            json=expected_request(scenario.api_key),
            timeout=ANKI_CONNECT_TIMEOUT_SEC,
        )
        response.raise_for_status.assert_called_once_with()

    @pytest.mark.parametrize("scenario", REQUEST_FAILURE_SCENARIOS.values(), ids=REQUEST_FAILURE_SCENARIOS.keys())
    def test_request_failure_is_classified(
        self, scenario: RequestFailureScenario, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Transport failures retain their details in the appropriate public exception type."""
        request_error = scenario.error_type(scenario.error_message)
        monkeypatch.setattr("lancet.anki.client.requests.post", Mock(side_effect=request_error))
        client = AnkiConnectClient(Config(anki_connect_url=DEFAULT_ANKICONNECT_URL))
        with pytest.raises(scenario.expected_error_type) as exc_info:
            client.invoke("findNotes", {"query": "added:1"})
        assert str(exc_info.value) == f"Could not reach AnkiConnect: {scenario.error_message}"


class TestAnkiNoteOperations:
    """Test note selection, field/media requests, and ordered image attachment behavior."""

    @pytest.mark.parametrize("scenario", NOTE_SELECTION_SCENARIOS.values(), ids=NOTE_SELECTION_SCENARIOS.keys())
    def test_last_added_note_id(self, scenario: NoteSelectionScenario, monkeypatch: pytest.MonkeyPatch) -> None:
        """The added:1 result selects the greatest ID or rejects a missing recent note."""
        client = AnkiConnectClient(Config(anki_connect_url=DEFAULT_ANKICONNECT_URL))
        invoke = Mock(return_value=list(scenario.note_ids))
        monkeypatch.setattr(client, "invoke", invoke)
        if scenario.expected_note_id is None:
            with pytest.raises(AnkiConnectError) as exc_info:
                client.last_added_note_id()
            assert str(exc_info.value) == scenario.expected_error_message
        else:
            assert client.last_added_note_id() == scenario.expected_note_id
        assert invoke.call_args == call("findNotes", {"query": "added:1"})

    @pytest.mark.parametrize("scenario", SIDE_EFFECT_SCENARIOS.values(), ids=SIDE_EFFECT_SCENARIOS.keys())
    def test_side_effect_actions_ignore_success_result(
        self, scenario: SideEffectScenario, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Side-effect operations rely on envelope validation and ignore unused success results."""
        client = AnkiConnectClient(Config(anki_connect_url=DEFAULT_ANKICONNECT_URL))
        invoke = Mock(return_value={"unexpected": "but successful"})
        monkeypatch.setattr(client, "invoke", invoke)
        invoke_side_effect(client, scenario)
        assert invoke.call_args == call(scenario.operation.value, expected_side_effect_params(scenario))

    @pytest.mark.parametrize("scenario", NOTE_FIELD_SCENARIOS.values(), ids=NOTE_FIELD_SCENARIOS.keys())
    def test_note_field_request(self, scenario: NoteFieldScenario, monkeypatch: pytest.MonkeyPatch) -> None:
        """notesInfo requests the target note and extracts its current field HTML."""
        client = AnkiConnectClient(Config(anki_connect_url=DEFAULT_ANKICONNECT_URL))
        invoke = Mock(return_value=[{"fields": {IMAGE_FIELD: {"value": scenario.current_value}}}])
        monkeypatch.setattr(client, "invoke", invoke)
        assert client.note_field(NOTE_ID, IMAGE_FIELD) == scenario.current_value
        assert invoke.call_args == call("notesInfo", {"notes": [NOTE_ID]})

    @pytest.mark.parametrize("scenario", STORE_MEDIA_SCENARIOS.values(), ids=STORE_MEDIA_SCENARIOS.keys())
    def test_store_media_request(self, scenario: StoreMediaScenario, monkeypatch: pytest.MonkeyPatch) -> None:
        """storeMediaFile receives base64 image bytes and returns Anki's assigned filename."""
        client = AnkiConnectClient(Config(anki_connect_url=DEFAULT_ANKICONNECT_URL))
        invoke = Mock(return_value=scenario.returned_filename)
        monkeypatch.setattr(client, "invoke", invoke)
        assert client.store_media(scenario.filename, IMAGE_DATA) == scenario.returned_filename
        assert invoke.call_args == call(
            "storeMediaFile",
            {"filename": scenario.filename, "data": "aW1hZ2U=", "deleteExisting": False},
        )

    @pytest.mark.parametrize("scenario", FILENAME_SCENARIOS.values(), ids=FILENAME_SCENARIOS.keys())
    def test_make_image_filename(self, scenario: FilenameScenario, monkeypatch: pytest.MonkeyPatch) -> None:
        """Generated media names include the note ID, exact timestamp, and image extension."""
        monkeypatch.setattr("lancet.anki.client.datetime.datetime", FixedDateTime)
        assert make_image_filename(scenario.note_id, scenario.container) == scenario.expected_filename

    @pytest.mark.parametrize("scenario", ATTACHMENT_SCENARIOS.values(), ids=ATTACHMENT_SCENARIOS.keys())
    def test_attach_appends_image_and_reselects_note(
        self, scenario: AttachmentScenario, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Attach validates content, inserts the separator, and reopens the target note."""
        setup = create_attachment_setup(scenario, monkeypatch)
        assert setup.client.attach_image(NOTE_ID, IMAGE_FIELD, setup.image) == "lancet_actual.webp"
        setup.filename_factory.assert_called_once_with(NOTE_ID, AnkiImageFormat.webp.value)
        assert setup.operations.calls == (
            AttachmentOperationCall(name=AttachmentOperation.browse_note, args=(0,)),
            AttachmentOperationCall(name=AttachmentOperation.note_field, args=(NOTE_ID, IMAGE_FIELD)),
            AttachmentOperationCall(name=AttachmentOperation.store_media, args=("lancet_actual.webp", IMAGE_DATA)),
            AttachmentOperationCall(
                name=AttachmentOperation.update_note_field,
                args=(NOTE_ID, IMAGE_FIELD, scenario.expected_html),
            ),
            AttachmentOperationCall(name=AttachmentOperation.browse_note, args=(NOTE_ID,)),
        )

    @pytest.mark.parametrize("scenario", CLEANUP_SCENARIOS.values(), ids=CLEANUP_SCENARIOS.keys())
    def test_failed_update_preserves_original_error(
        self, scenario: CleanupScenario, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Media rollback never masks the original update failure, even when cleanup also fails."""
        attachment = create_attachment_setup(ATTACHMENT_SCENARIOS["default_break"], monkeypatch)
        expected_error = AnkiConnectError(UPDATE_ERROR_MESSAGE)
        monkeypatch.setattr(attachment.client, "update_note_field", Mock(side_effect=expected_error))
        cleanup_error = scenario.cleanup_error_type("cleanup failed") if scenario.cleanup_error_type else None
        delete_media = Mock(side_effect=cleanup_error)
        monkeypatch.setattr(attachment.client, "delete_media", delete_media)
        with pytest.raises(AnkiConnectError) as exc_info:
            attachment.client.attach_image(NOTE_ID, IMAGE_FIELD, attachment.image)
        assert exc_info.value is expected_error
        assert delete_media.call_args == call("lancet_actual.webp")


class JoinHtmlScenario(typing.NamedTuple):
    """Two HTML fragments, a separator, and the exact joined field value."""

    old_content: str
    new_content: str
    separator: str
    expected: str


JOIN_HTML_SCENARIOS: dict[str, JoinHtmlScenario] = {
    "preserves_meaningful_whitespace": JoinHtmlScenario(
        old_content="  old  ",
        new_content="  new  ",
        separator="<br>",
        expected="  old  <br>  new  ",
    ),
    "whitespace_only_old_content": JoinHtmlScenario(
        old_content="   ",
        new_content="<img>",
        separator="<br>",
        expected="<img>",
    ),
    "whitespace_only_new_content": JoinHtmlScenario(
        old_content="old",
        new_content="   ",
        separator="<br>",
        expected="old",
    ),
    "empty_separator": JoinHtmlScenario(
        old_content="old",
        new_content="new",
        separator="",
        expected="oldnew",
    ),
}


class TestJoinHtmlContent:
    """Test semantic emptiness and exact HTML preservation when appending media."""

    @pytest.mark.parametrize("scenario", JOIN_HTML_SCENARIOS.values(), ids=JOIN_HTML_SCENARIOS.keys())
    def test_preserves_non_empty_fragments(self, scenario: JoinHtmlScenario) -> None:
        """Whitespace decides emptiness but never modifies retained HTML."""
        assert (
            join_html_content(scenario.old_content, scenario.new_content, sep=scenario.separator) == scenario.expected
        )
