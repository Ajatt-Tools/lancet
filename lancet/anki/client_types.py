# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
import dataclasses
import typing
from collections.abc import Sequence


class FindNotesParams(typing.TypedDict):
    """
    Parameters for AnkiConnect's findNotes action.
    https://git.sr.ht/~foosoft/anki-connect/tree/master/item/README.md#codefindnotescode
    """

    query: str


class NotesInfoParams(typing.TypedDict):
    """
    Parameters for AnkiConnect's notesInfo action.
    https://git.sr.ht/~foosoft/anki-connect/tree/master/item/README.md#codenotesinfocode
    """

    notes: Sequence[int]


class StoreMediaFileParams(typing.TypedDict):
    """
    Parameters for AnkiConnect's storeMediaFile action.
    https://git.sr.ht/~foosoft/anki-connect/tree/master/item/README.md#codestoremediafilecode
    """

    filename: str
    data: str
    deleteExisting: bool  # Any existing file with the same name is deleted by default.


class UpdateNoteFieldsNote(typing.TypedDict):
    """
    The note object passed to updateNoteFields.
    https://git.sr.ht/~foosoft/anki-connect/tree/master/item/README.md#codeupdatenotefieldscode
    """

    id: int
    fields: dict[str, str]  # Mapping from field name to field content.


class UpdateNoteFieldsParams(typing.TypedDict):
    """Parameters for AnkiConnect's updateNoteFields action."""

    note: UpdateNoteFieldsNote


class GuiBrowseParams(typing.TypedDict):
    """
    Parameters for AnkiConnect's guiBrowse action.
    https://git.sr.ht/~foosoft/anki-connect/tree/master/item/README.md#codeguibrowsecode
    """

    query: str


class DeleteMediaFileParams(typing.TypedDict):
    """
    Parameters for AnkiConnect's deleteMediaFile action.
    https://git.sr.ht/~foosoft/anki-connect/tree/master/item/README.md#codedeletemediafilecode
    """

    filename: str


type AnkiConnectParams = (
    FindNotesParams
    | NotesInfoParams
    | StoreMediaFileParams
    | UpdateNoteFieldsParams
    | GuiBrowseParams
    | DeleteMediaFileParams
)


class AnkiConnectRequest(typing.TypedDict):
    """A version-six AnkiConnect request payload."""

    action: str
    version: int
    params: AnkiConnectParams
    key: typing.NotRequired[str]


type AnkiConnectResult = object
