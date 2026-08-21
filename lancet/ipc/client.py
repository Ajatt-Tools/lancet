# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import http.client
import json
import typing

from lancet.actions import LancetAction
from lancet.config import Config
from lancet.exceptions import (
    LancetException,
    LancetIpcConnectError,
    LancetIpcParseError,
)
from lancet.ipc.consts import IPC_COMMAND_PATH, IPC_ENCODING, IPC_HOST, IPC_TIMEOUT_SEC
from lancet.ipc.types import (
    IpcRequest,
    IpcResponse,
    IpcStatus,
    RequestPayloadDict,
    ResponsePayloadDict,
)


def decode_response(body: str) -> IpcResponse:
    """Parse a JSON response body into an "IpcResponse"."""
    try:
        data = typing.cast(ResponsePayloadDict, json.loads(body))
    except json.JSONDecodeError as ex:
        raise LancetIpcParseError(f"Failed to parse JSON: {ex}") from ex
    try:
        status = IpcStatus[data["status"]]
    except KeyError as ex:
        raise LancetIpcParseError(f"Status was not received: {ex}") from ex
    except TypeError as ex:
        raise LancetIpcParseError(f"Response was not a JSON object: {ex}") from ex
    return IpcResponse(status=status, message=str(data.get("message", "")))


class LancetIpcClient:
    """HTTP client for sending commands to the running Lancet daemon."""

    def __init__(self, cfg: Config) -> None:
        """Initialize the client with the daemon connection configuration."""
        self._cfg = cfg

    def send_ipc_request(self, request: IpcRequest) -> IpcResponse:
        """
        Send an "IpcRequest" to the running daemon over HTTP and return the parsed "IpcResponse".

        Raises "LancetIpcConnectError" if the daemon is not reachable.
        """
        payload: RequestPayloadDict = {"action": request.action.name}
        body = json.dumps(payload).encode(IPC_ENCODING)
        conn = http.client.HTTPConnection(IPC_HOST, self._cfg.bind_port, timeout=IPC_TIMEOUT_SEC)
        try:
            conn.request(
                "POST",
                IPC_COMMAND_PATH,
                body=body,
                headers={"Content-Type": "application/json", "Content-Length": str(len(body))},
            )
            return decode_response(conn.getresponse().read().decode(IPC_ENCODING))
        except OSError as ex:
            raise LancetIpcConnectError(f"Could not reach the running Lancet instance: {ex}") from ex
        finally:
            conn.close()

    def _send_and_handle_error(self, r: IpcRequest) -> IpcResponse:
        """Send a request, returning an error response if the connection fails."""
        try:
            return self.send_ipc_request(r)
        except LancetException as ex:
            return IpcResponse(status=IpcStatus.error, message=str(ex))

    def ask_screenshot(self) -> IpcResponse:
        """Tell the running daemon to open the screenshot area selector."""
        return self._send_and_handle_error(IpcRequest(action=LancetAction.screenshot))

    def ask_ocr(self, detect: bool) -> IpcResponse:
        """Tell the running daemon to run OCR, optionally with speech-bubble detection."""
        return self._send_and_handle_error(
            IpcRequest(action=LancetAction.detect_and_ocr if detect else LancetAction.ocr)
        )
