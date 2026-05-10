# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import enum
import typing
from http import HTTPStatus

from lancet.actions import LancetAction


class IpcStatus(enum.Enum):
    """Status field values in IPC responses."""

    ok = "ok"
    error = "error"


class RequestPayloadDict(typing.TypedDict):
    action: str


class IpcRequest(typing.NamedTuple):
    """A command sent from a CLI invocation to the running daemon."""

    action: LancetAction


class IpcResponse(typing.NamedTuple):
    """A response sent from the daemon back to the CLI invocation."""

    status: IpcStatus
    message: str


class ResponsePayloadDict(typing.TypedDict):
    status: str
    message: str


class IpcStatusCode(typing.NamedTuple):
    """HTTP status code and its phrase, extracted from an HTTPStatus enum member."""

    code: int
    phrase: str

    @classmethod
    def new(cls, status: HTTPStatus) -> typing.Self:
        """Convert an HTTPStatus enum member to a StatusCode."""
        return cls(code=status.value, phrase=status.phrase)
