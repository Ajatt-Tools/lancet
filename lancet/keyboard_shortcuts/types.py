# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
import dataclasses
import enum
import typing
from collections.abc import MutableSequence
from typing import Callable

from pynput.keyboard import KeyCode, Key

QtShortcutStr = typing.NewType("QtShortcutStr", str)
PyShortcutStr = typing.NewType("PyShortcutStr", str)


class LancetShortcutEnum(enum.Enum):
    """Enum identifying the available keyboard shortcut actions."""

    ocr_shortcut = enum.auto()
    ocr_page_shortcut = enum.auto()
    screenshot_shortcut = enum.auto()


class ShortcutParseFailure(typing.NamedTuple):
    """Records a single shortcut that failed to parse."""

    action: LancetShortcutEnum
    shortcut: str
    error: str


@dataclasses.dataclass(frozen=True)
class ShortcutConversionResult:
    """
    Result of converting a batch of shortcuts to pynput format.
    The list of failures gets appended to, thus marked as mutable.
    """

    hotkeys: dict[PyShortcutStr, LancetShortcutEnum] = dataclasses.field(default_factory=dict)
    failures: MutableSequence[ShortcutParseFailure] = dataclasses.field(default_factory=list)

    def format_failures(self) -> str:
        """Return a formatted message if any shortcuts failed to convert."""
        if not self.failures:
            return ""
        detail = "; ".join(f"{f.action.name}={f.shortcut!r} ({f.error})" for f in self.failures)
        return f"failed to parse {len(self.failures)} shortcut(s): {detail}"


class ParsedEntry(typing.NamedTuple):
    """A parsed hotkey entry: the original shortcut string, its key set, and its callback."""

    shortcut: PyShortcutStr
    key_set: frozenset[KeyCode | Key]
    action: Callable[[], None]
