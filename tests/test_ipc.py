# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""
Tests for the IPC protocol: parsing, encoding, and real HTTP request/response.
"""

import http.client
import io
import json
import socket
import typing
from collections.abc import Generator
from http import HTTPStatus
from unittest.mock import patch

import pytest

from lancet.actions import LancetAction
from lancet.config import Config
from lancet.exceptions import LancetIpcParseError
from lancet.ipc.client import LancetIpcClient, decode_response
from lancet.ipc.consts import IPC_COMMAND_PATH, IPC_ENCODING, IPC_HOST, IPC_TIMEOUT_SEC
from lancet.ipc.server import (
    IpcServer,
    encode_response,
    parse_ipc_request,
)
from lancet.ipc.types import IpcRequest, IpcResponse, IpcStatus

EPHEMERAL_PORT: typing.Final[int] = 0
"""Port 0 tells the OS to assign a random available port, avoiding conflicts in parallel tests."""


@pytest.fixture
def ipc_server() -> Generator[IpcServer]:
    """Start an IpcServer on an ephemeral port and shut it down after the test."""
    with IpcServer(Config(bind_port=EPHEMERAL_PORT)) as ipc:
        yield ipc


class ParseScenario(typing.NamedTuple):
    """A scenario for parse_ipc_request testing."""

    body: str
    expected_request: IpcRequest | None
    expected_error: type[Exception] | None


VALID_REQUEST_SCENARIOS: dict[str, ParseScenario] = {
    "valid_ocr": ParseScenario(
        body='{"action": "ocr"}',
        expected_request=IpcRequest(action=LancetAction.ocr),
        expected_error=None,
    ),
    "valid_detect_and_ocr": ParseScenario(
        body='{"action": "detect_and_ocr"}',
        expected_request=IpcRequest(action=LancetAction.detect_and_ocr),
        expected_error=None,
    ),
    "valid_screenshot": ParseScenario(
        body='{"action": "screenshot"}',
        expected_request=IpcRequest(action=LancetAction.screenshot),
        expected_error=None,
    ),
    "extra_fields_ignored": ParseScenario(
        body='{"action": "ocr", "image_path": "/foo/bar.png"}',
        expected_request=IpcRequest(action=LancetAction.ocr),
        expected_error=None,
    ),
}


INVALID_REQUEST_SCENARIOS: dict[str, ParseScenario] = {
    "missing_action": ParseScenario(body="{}", expected_request=None, expected_error=LancetIpcParseError),
    "invalid_action": ParseScenario(
        body='{"action": "invalid"}', expected_request=None, expected_error=LancetIpcParseError
    ),
    "malformed_json": ParseScenario(body="{not json", expected_request=None, expected_error=LancetIpcParseError),
    "null_body": ParseScenario(body="null", expected_request=None, expected_error=LancetIpcParseError),
    "array_body": ParseScenario(body="[]", expected_request=None, expected_error=LancetIpcParseError),
    "string_body": ParseScenario(body='"ocr"', expected_request=None, expected_error=LancetIpcParseError),
}


PARSE_SCENARIOS: dict[str, ParseScenario] = {
    **VALID_REQUEST_SCENARIOS,
    **INVALID_REQUEST_SCENARIOS,
}


class TestParseIpcRequest:
    """Test that parse_ipc_request validates JSON and LancetAction values."""

    @pytest.mark.parametrize("scenario", PARSE_SCENARIOS.values(), ids=PARSE_SCENARIOS.keys())
    def test_parse_requests(self, scenario: ParseScenario) -> None:
        if scenario.expected_error is None:
            result = parse_ipc_request(scenario.body)
            assert result == scenario.expected_request
        else:
            with pytest.raises(scenario.expected_error):
                parse_ipc_request(scenario.body)


ENCODE_RESPONSE_SCENARIOS: dict[str, IpcResponse] = {
    "ok_with_message": IpcResponse(status=IpcStatus.ok, message="ocr command accepted"),
    "ok_without_message": IpcResponse(status=IpcStatus.ok, message=""),
    "error_with_message": IpcResponse(status=IpcStatus.error, message="unknown action"),
}

DECODE_RESPONSE_ERRORS: dict[str, str] = {
    "missing_status": '{"message": "ok"}',
    "invalid_status": '{"status": "bogus", "message": "ok"}',
    "status_not_string": '{"status": null, "message": "ok"}',
    "malformed_json": "{not json",
    "null_body": "null",
    "array_body": "[]",
    "string_body": '"ok"',
}


class TestDecodeResponse:
    """Test that decode_response parses valid bodies and rejects invalid bodies."""

    @pytest.mark.parametrize("response", ENCODE_RESPONSE_SCENARIOS.values(), ids=ENCODE_RESPONSE_SCENARIOS.keys())
    def test_encode_then_decode(self, response: IpcResponse) -> None:
        encoded = encode_response(response)
        decoded = decode_response(encoded.decode(IPC_ENCODING))
        assert decoded == response

    @pytest.mark.parametrize("body", DECODE_RESPONSE_ERRORS.values(), ids=DECODE_RESPONSE_ERRORS.keys())
    def test_decode_error(self, body: str) -> None:
        with pytest.raises(LancetIpcParseError):
            decode_response(body)


class SendScenario(typing.NamedTuple):
    """A scenario for end-to-end HTTP request/response testing."""

    action: LancetAction
    expected_message: str


SEND_SCENARIOS: dict[str, SendScenario] = {
    "ocr": SendScenario(
        action=LancetAction.ocr,
        expected_message="ocr command accepted",
    ),
    "screenshot": SendScenario(
        action=LancetAction.screenshot,
        expected_message="screenshot command accepted",
    ),
    "detect_and_ocr": SendScenario(
        action=LancetAction.detect_and_ocr,
        expected_message="detect_and_ocr command accepted",
    ),
}


class TestSendIpcRequest:
    """Test that send_ipc_request sends an HTTP POST and returns a correctly parsed response."""

    @pytest.mark.parametrize("scenario", SEND_SCENARIOS.values(), ids=SEND_SCENARIOS.keys())
    def test_send_ipc_request(self, ipc_server: IpcServer, scenario: SendScenario) -> None:
        """Send each command over a real HTTP port and verify the response and signal emission."""
        received_actions: list[LancetAction] = []

        def mock_q_emit(_signal: object, action: LancetAction) -> None:
            received_actions.append(action)

        client = LancetIpcClient(Config(bind_port=ipc_server.server_address[1]))
        with patch("lancet.ipc.server.q_emit", mock_q_emit):
            response = client.send_ipc_request(IpcRequest(action=scenario.action))
        assert response.status == IpcStatus.ok
        assert response.message == scenario.expected_message
        assert received_actions == [scenario.action]


def raw_post(port: int, path: str, body: bytes) -> http.client.HTTPResponse:
    """
    Send an HTTP POST and return the response.

    Uses http.client.HTTPConnection so that connection failures surface as
    OSError instead of being wrapped in LancetIpcConnectError.
    """
    conn = http.client.HTTPConnection(IPC_HOST, port, timeout=IPC_TIMEOUT_SEC)
    try:
        conn.request(
            "POST",
            path,
            body=body,
            headers={"Content-Type": "application/json", "Content-Length": str(len(body))},
        )
        return conn.getresponse()
    finally:
        conn.close()


def raw_post_no_length(port: int, path: str) -> tuple[int, bytes]:
    """
    Send a raw HTTP POST with no Content-Length header using a raw socket.

    Returns (status_code, body_bytes). Used to test handling of missing Content-Length.
    """
    buf = io.StringIO()
    buf.write(f"POST {path} HTTP/1.1\r\n")
    buf.write(f"Host: {IPC_HOST}:{port}\r\n")
    buf.write("Content-Type: application/json\r\n")
    buf.write("Connection: close\r\n")
    buf.write("\r\n")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.settimeout(IPC_TIMEOUT_SEC)
        sock.connect((IPC_HOST, port))
        sock.sendall(buf.getvalue().encode(IPC_ENCODING))
        response_bytes = b""
        while chunk := sock.recv(4096):
            response_bytes += chunk
        response_str = response_bytes.decode(IPC_ENCODING, errors="replace")
        status_line, _, body_str = response_str.partition("\r\n\r\n")
        status_code = int(status_line.split(" ")[1])
        return status_code, body_str.encode(IPC_ENCODING)
    finally:
        sock.close()


class ErrorScenario(typing.NamedTuple):
    """A scenario for IPC error-path testing."""

    path: str
    body: bytes
    expected_http_status: int
    expected_ipc_status: IpcStatus


ERROR_SCENARIOS: dict[str, ErrorScenario] = {
    "wrong_path": ErrorScenario(
        path="/nonexistent",
        body=json.dumps({"action": "ocr"}).encode(IPC_ENCODING),
        expected_http_status=HTTPStatus.NOT_FOUND.value,
        expected_ipc_status=IpcStatus.error,
    ),
    **{
        name: ErrorScenario(
            path=IPC_COMMAND_PATH,
            body=scenario.body.encode(IPC_ENCODING),
            expected_http_status=HTTPStatus.BAD_REQUEST.value,
            expected_ipc_status=IpcStatus.error,
        )
        for name, scenario in INVALID_REQUEST_SCENARIOS.items()
    },
}


class TestIpcErrorResponses:
    """Test that malformed requests return structured error responses instead of crashing."""

    @pytest.mark.parametrize("scenario", ERROR_SCENARIOS.values(), ids=ERROR_SCENARIOS.keys())
    def test_error_response(self, ipc_server: IpcServer, scenario: ErrorScenario) -> None:
        """Send a bad request over HTTP and verify the server returns a structured error."""
        port = ipc_server.server_address[1]
        with patch("lancet.ipc.server.q_emit"):
            resp = raw_post(port, scenario.path, scenario.body)
        assert resp.status == scenario.expected_http_status
        data = json.loads(resp.read().decode(IPC_ENCODING))
        assert data["status"] == scenario.expected_ipc_status.name
        assert data["message"] != ""

    def test_missing_content_length_returns_400(self, ipc_server: IpcServer) -> None:
        """A request without Content-Length header returns HTTP 400, not a crash."""
        port = ipc_server.server_address[1]
        status_code, body_bytes = raw_post_no_length(port, IPC_COMMAND_PATH)
        assert status_code == HTTPStatus.BAD_REQUEST.value
        data = json.loads(body_bytes.decode(IPC_ENCODING))
        assert data["status"] == IpcStatus.error.name
        assert data["message"] != ""
