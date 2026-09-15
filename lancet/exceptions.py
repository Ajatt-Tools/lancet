# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
from http import HTTPStatus

from PyQt6.QtWidgets import QWidget

from lancet.config import CfgValueTypes
from lancet.ipc.types import IpcStatusCode


class LancetException(Exception):
    pass


class ConfigReadError(LancetException, RuntimeError):
    """Raised when the configuration file cannot be read or parsed."""

    pass


class PortAlreadyInUseError(LancetException, OSError):
    pass


class PixmapConversionError(LancetException, ValueError):
    pass


class LancetHTTPError(LancetException, OSError):
    pass


class AnkiConnectError(LancetException, RuntimeError):
    """Raised when AnkiConnect cannot complete a requested operation."""

    pass


class AnkiConnectUnavailableError(AnkiConnectError):
    """Raised when Lancet cannot establish a connection to AnkiConnect."""

    @property
    def what(self) -> str:
        """Return a concise user-facing explanation."""
        return "AnkiConnect isn't running."


class AnkiAttachmentInProgressError(AnkiConnectError):
    """Raised when another Lancet attachment transaction already owns Anki media updates."""

    pass


class AnkiAttachmentCancelledError(AnkiConnectError):
    """Raised when a dialog prevents an Anki attachment from opening selection."""

    @property
    def what(self) -> str:
        """Return a concise user-facing cancellation explanation."""
        return "Anki attachment skipped because a dialog is open."


class AnkiImageEncodingError(LancetException, RuntimeError):
    """Raised when Pillow cannot encode the configured Anki image format."""

    pass


class KeyboardShortcutParseError(LancetException, ValueError):
    """Raised when a keyboard shortcut string cannot be converted to pynput format."""

    pass


class DuplicateShortcutError(KeyboardShortcutParseError):
    """Raised when two registered shortcuts resolve to the same set of keys."""

    pass


class LancetIpcParseError(LancetException, ValueError):
    """Raised when parsing an IPC request or response fails."""

    pass


class LancetIpcConnectError(LancetException, RuntimeError):
    """Raised when a CLI command cannot connect to the running Lancet daemon."""

    pass


class IpcRequestError(LancetException, ValueError):
    """Raised inside do_POST when the request cannot be processed."""

    _status: IpcStatusCode

    def __init__(self, *, status: HTTPStatus, message: str) -> None:
        self._status = IpcStatusCode.new(status)
        super().__init__(message)

    @property
    def status(self) -> IpcStatusCode:
        return self._status


class WidgetSetValueError(ValueError):
    def __init__(self, widget: QWidget, value: CfgValueTypes) -> None:
        super().__init__(
            f"Can't handle widget of type {type(widget).__name__} and value of type {type(value).__name__}"
        )
