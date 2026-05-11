# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import http.server
import json
import threading
import typing
from http import HTTPStatus

from loguru import logger
from PyQt6.QtCore import QObject, pyqtSignal
from zala.utils import q_emit

from lancet.actions import LancetAction
from lancet.config import Config
from lancet.exceptions import (
    IpcRequestError,
    LancetIpcParseError,
    PortAlreadyInUseError,
)
from lancet.ipc.consts import IPC_COMMAND_PATH, IPC_ENCODING, IPC_HOST
from lancet.ipc.types import (
    IpcRequest,
    IpcResponse,
    IpcStatus,
    RequestPayloadDict,
    ResponsePayloadDict,
)


def parse_ipc_request(body: str) -> IpcRequest:
    """
    Parse a JSON request body into an "IpcRequest".

    Raises "LancetIpcParseError" if "action" is missing or not a valid "LancetAction".
    Raises "LancetIpcParseError" if the body is not valid JSON.
    """
    try:
        data: RequestPayloadDict = typing.cast(RequestPayloadDict, json.loads(body))
    except json.JSONDecodeError as ex:
        raise LancetIpcParseError(f"Failed to parse JSON: {ex}") from ex
    try:
        action = LancetAction[data["action"]]
    except KeyError as ex:
        raise LancetIpcParseError(f"Unknown action '{data.get('action')}': {ex}") from ex
    return IpcRequest(action=action)


def encode_response(response: IpcResponse) -> bytes:
    """Serialize an "IpcResponse" to UTF-8 JSON bytes."""
    payload: ResponsePayloadDict = {"status": response.status.name, "message": response.message}
    return json.dumps(payload).encode(IPC_ENCODING)


class IpcSignals(QObject):
    """Qt signal bridge between the http.server background thread and the Qt main thread."""

    command_received = pyqtSignal(LancetAction)


class IpcRequestHandler(http.server.BaseHTTPRequestHandler):
    """Handle POST /command requests from lancet CLI invocations."""

    server: LancetIpcHTTPServer

    def do_POST(self) -> None:
        """Parse the JSON body, emit the action on the Qt main thread, and respond."""
        try:
            request = self._parse_request()
        except IpcRequestError as ex:
            self._respond(ex.status.code, IpcResponse(status=IpcStatus.error, message=str(ex)))
        else:
            q_emit(self.server.signals.command_received, request.action)
            self._respond(
                HTTPStatus.OK, IpcResponse(status=IpcStatus.ok, message=f"{request.action.name} command accepted")
            )

    def _parse_request(self) -> IpcRequest:
        """Validate the request path, Content-Length, and JSON body, raising on error."""
        if self.path != IPC_COMMAND_PATH:
            raise IpcRequestError(status=HTTPStatus.NOT_FOUND, message=f"unknown path: {self.path}")
        try:
            length = int(self.headers["Content-Length"])
        except (KeyError, TypeError, ValueError) as ex:
            raise IpcRequestError(status=HTTPStatus.BAD_REQUEST, message=f"Invalid Content-Length: {ex}") from ex

        try:
            return parse_ipc_request(body=self.rfile.read(length).decode(IPC_ENCODING))
        except UnicodeDecodeError as ex:
            raise IpcRequestError(status=HTTPStatus.BAD_REQUEST, message=f"Invalid JSON: {ex}") from ex
        except LancetIpcParseError as ex:
            raise IpcRequestError(status=HTTPStatus.BAD_REQUEST, message=str(ex)) from ex

    def _respond(self, status: int, response: IpcResponse) -> None:
        """Write an HTTP response with a JSON body."""
        data = encode_response(response)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt: str, *args: object) -> None:
        """Route http.server access log through loguru instead of stderr."""
        logger.debug(fmt % args)


class LancetIpcHTTPServer(http.server.HTTPServer):
    """
    HTTPServer subclass that holds a reference to IpcSignals for use by request handlers.

    Uses HTTPServer rather than ThreadingHTTPServer because the IPC channel handles
    one CLI command at a time (tiny JSON POST, immediate acknowledgment).
    ThreadingHTTPServer would spawn a thread per request, adding overhead and
    concurrency concerns (e.g. concurrent q_emit calls) with no benefit for
    sequential localhost-only traffic.
    """

    _signals: IpcSignals

    def __init__(
        self,
        server_address: tuple[str, int],
        *,
        handler_class: type[IpcRequestHandler],
        signals: IpcSignals,
        bind_and_activate: bool = True,
    ) -> None:
        super().__init__(server_address, RequestHandlerClass=handler_class, bind_and_activate=bind_and_activate)
        self._signals = signals

    @property
    def signals(self) -> IpcSignals:
        return self._signals


class IpcServer:
    """
    Manages the IPC HTTP server lifecycle in a background daemon thread.

    Follows the LancetShortcutManager pattern: owns signals (stable across restarts),
    owns a server instance, and owns a listener thread. Callers interact only with
    start(), shutdown(), and the signals attribute.
    """

    _signals: IpcSignals
    _server: LancetIpcHTTPServer
    _thread: threading.Thread

    def __init__(self, cfg: Config) -> None:
        """
        Construct an IpcHTTPServer bound to 127.0.0.1:port.

        Raises PortAlreadyInUseError if the port is already in use (daemon already running).
        """
        self._cfg = cfg
        self._signals = IpcSignals()
        try:
            self._server = LancetIpcHTTPServer(
                (IPC_HOST, self._cfg.bind_port), handler_class=IpcRequestHandler, signals=self._signals
            )
        except OSError as ex:
            raise PortAlreadyInUseError(f"Another instance of this program is already running: {ex}") from ex
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def signals(self) -> IpcSignals:
        return self._signals

    @property
    def server_address(self) -> tuple[str, int]:
        """Return the (host, port) this server is bound to."""
        return self._server.server_address  # type: ignore[return-value]

    def start(self) -> None:
        """Start the IPC server in a background daemon thread."""
        self._thread.start()

    def shutdown(self) -> None:
        """Stop the server and join the background thread."""
        self._server.shutdown()
        self._thread.join()

    def __enter__(self) -> typing.Self:
        """Start the server and return self."""
        self.start()
        return self

    def __exit__(self, *args: object) -> None:
        """Shut down the server."""
        self.shutdown()
