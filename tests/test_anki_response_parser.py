# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Tests for strict AnkiConnect response parsing."""

import json
import typing
from collections.abc import Callable
from unittest.mock import create_autospec

import pytest
import requests

from lancet.anki.response_parser import (
    parse_anki_response,
    parse_media_filename,
    parse_note_field,
    parse_note_ids,
)
from lancet.exceptions import AnkiConnectError

NOTE_ID = 42
IMAGE_FIELD = "Image"


class EnvelopeScenario(typing.NamedTuple):
    """Immutable decoded-response inputs and one expected parser outcome."""

    payload_json: str
    json_error_type: type[ValueError] | None
    json_error_message: str
    expected_json: str | None
    expected_error: str | None


ENVELOPE_SCENARIOS: dict[str, EnvelopeScenario] = {
    "success": EnvelopeScenario(
        payload_json='{"result": [1], "error": null}',
        json_error_type=None,
        json_error_message="",
        expected_json="[1]",
        expected_error=None,
    ),
    "api_error": EnvelopeScenario(
        payload_json='{"result": null, "error": "note missing"}',
        json_error_type=None,
        json_error_message="",
        expected_json=None,
        expected_error="note missing",
    ),
    "non_object": EnvelopeScenario(
        payload_json="[]",
        json_error_type=None,
        json_error_message="",
        expected_json=None,
        expected_error="AnkiConnect response is not a JSON object",
    ),
    "missing_field": EnvelopeScenario(
        payload_json='{"result": null}',
        json_error_type=None,
        json_error_message="",
        expected_json=None,
        expected_error="AnkiConnect response is missing result or error",
    ),
    "invalid_error": EnvelopeScenario(
        payload_json='{"result": null, "error": 7}',
        json_error_type=None,
        json_error_message="",
        expected_json=None,
        expected_error="AnkiConnect response has an invalid error field",
    ),
    "invalid_json": EnvelopeScenario(
        payload_json="{}",
        json_error_type=ValueError,
        json_error_message="bad json",
        expected_json=None,
        expected_error="AnkiConnect returned invalid JSON: bad json",
    ),
}


class TestParseAnkiResponse:
    """Test common AnkiConnect envelope and JSON validation."""

    @pytest.mark.parametrize("scenario", ENVELOPE_SCENARIOS.values(), ids=ENVELOPE_SCENARIOS.keys())
    def test_parse(self, scenario: EnvelopeScenario) -> None:
        """Each envelope returns its result or raises its exact public parsing error."""
        response = create_autospec(requests.Response, instance=True)
        json_error = scenario.json_error_type(scenario.json_error_message) if scenario.json_error_type else None
        response.json.return_value = json.loads(scenario.payload_json)
        response.json.side_effect = json_error
        if scenario.expected_error is None:
            assert parse_anki_response(response) == json.loads(scenario.expected_json or "null")
            return
        with pytest.raises(AnkiConnectError) as exc_info:
            parse_anki_response(response)
        assert str(exc_info.value) == scenario.expected_error
        if json_error is not None:
            assert exc_info.value.__cause__ is json_error


class ResultScenario(typing.NamedTuple):
    """An action-specific parser, immutable input, and exact expected outcome."""

    parser: Callable[[object], object]
    value_json: str
    expected_json: str | None
    expected_error: str | None


RESULT_SCENARIOS: dict[str, ResultScenario] = {
    "note_ids": ResultScenario(parser=parse_note_ids, value_json="[1, 2]", expected_json="[1, 2]", expected_error=None),
    "note_ids_non_list": ResultScenario(
        parser=parse_note_ids,
        value_json="null",
        expected_json=None,
        expected_error="AnkiConnect returned an invalid list of IDs",
    ),
    "note_ids_reject_strings": ResultScenario(
        parser=parse_note_ids,
        value_json='["1"]',
        expected_json=None,
        expected_error="AnkiConnect returned an invalid list of IDs",
    ),
    "note_ids_reject_bool": ResultScenario(
        parser=parse_note_ids,
        value_json="[true]",
        expected_json=None,
        expected_error="AnkiConnect returned an invalid list of IDs",
    ),
    "media_filename": ResultScenario(
        parser=parse_media_filename,
        value_json='"image.avif"',
        expected_json='"image.avif"',
        expected_error=None,
    ),
    "media_filename_invalid": ResultScenario(
        parser=parse_media_filename,
        value_json="7",
        expected_json=None,
        expected_error="AnkiConnect returned an invalid media filename",
    ),
}


class TestActionResultParsers:
    """Test strict action-specific result validation."""

    @pytest.mark.parametrize("scenario", RESULT_SCENARIOS.values(), ids=RESULT_SCENARIOS.keys())
    def test_parse(self, scenario: ResultScenario) -> None:
        """Each parser accepts only the result shape promised by AnkiConnect."""
        if scenario.expected_error is None:
            assert scenario.parser(json.loads(scenario.value_json)) == json.loads(scenario.expected_json or "null")
            return
        with pytest.raises(AnkiConnectError) as exc_info:
            scenario.parser(json.loads(scenario.value_json))
        assert str(exc_info.value) == scenario.expected_error


class NoteFieldScenario(typing.NamedTuple):
    """An immutable notesInfo result and exact requested-field outcome."""

    result_json: str
    expected: str | None
    expected_error: str | None


NOTE_FIELD_SCENARIOS: dict[str, NoteFieldScenario] = {
    "valid": NoteFieldScenario(
        result_json='[{"fields": {"Image": {"value": "<img>"}}}]', expected="<img>", expected_error=None
    ),
    "result_non_list": NoteFieldScenario(
        result_json="null", expected=None, expected_error="Anki note 42 was not found"
    ),
    "note_missing": NoteFieldScenario(result_json="[]", expected=None, expected_error="Anki note 42 was not found"),
    "note_info_non_dict": NoteFieldScenario(
        result_json="[null]", expected=None, expected_error="AnkiConnect returned invalid note information"
    ),
    "fields_non_dict": NoteFieldScenario(
        result_json='[{"fields": []}]', expected=None, expected_error="AnkiConnect returned invalid note information"
    ),
    "field_missing": NoteFieldScenario(
        result_json='[{"fields": {}}]', expected=None, expected_error="Anki note does not have an 'Image' field"
    ),
    "field_non_dict": NoteFieldScenario(
        result_json='[{"fields": {"Image": null}}]',
        expected=None,
        expected_error="AnkiConnect returned an invalid value for field 'Image'",
    ),
    "value_invalid": NoteFieldScenario(
        result_json='[{"fields": {"Image": {"value": 7}}}]',
        expected=None,
        expected_error="AnkiConnect returned an invalid value for field 'Image'",
    ),
}


class TestParseNoteField:
    """Test nested notesInfo field extraction."""

    @pytest.mark.parametrize("scenario", NOTE_FIELD_SCENARIOS.values(), ids=NOTE_FIELD_SCENARIOS.keys())
    def test_parse(self, scenario: NoteFieldScenario) -> None:
        """The parser validates one note and returns only a string field value."""
        if scenario.expected_error is None:
            assert (
                parse_note_field(json.loads(scenario.result_json), note_id=NOTE_ID, field_name=IMAGE_FIELD)
                == scenario.expected
            )
            return
        with pytest.raises(AnkiConnectError) as exc_info:
            parse_note_field(json.loads(scenario.result_json), note_id=NOTE_ID, field_name=IMAGE_FIELD)
        assert str(exc_info.value) == scenario.expected_error
