# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
from http import HTTPStatus

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
