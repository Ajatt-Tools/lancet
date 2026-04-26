# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
import functools
import typing
from collections.abc import Callable

from loguru import logger
from pynput.keyboard import GlobalHotKeys, Key
from PyQt6.QtCore import QObject, pyqtSignal
from zala.utils import q_emit

from lancet.exceptions import KeyboardShortcutParseError
from lancet.keyboard_shortcuts.types import (
    LancetShortcutEnum,
    PyShortcutStr,
    QtShortcutStr,
    ShortcutConversionResult,
    ShortcutParseFailure,
)

# Canonical pynput special-key names, derived from the pynput.keyboard.Key enum.
# This ensures we stay in sync with whatever pynput version is installed.
PYNPUT_KEY_NAMES: typing.Final[frozenset[str]] = frozenset(key.name for key in Key)

# Aliases: maps user/Qt spellings to canonical pynput names.
# Includes modifier mappings (Qt's "Meta" is Win/Super/Cmd, pynput calls all of them "cmd")
# and common abbreviations that Qt and users produce (e.g. "Del" instead of "Delete").
KEY_ALIASES: typing.Final[dict[str, str]] = {
    "control": "ctrl",
    "meta": "cmd",
    "super": "cmd",
    "win": "cmd",
    "del": "delete",
    "escape": "esc",
    "return": "enter",
    "pgup": "page_up",
    "pgdown": "page_down",
}

# All pynput modifier names (canonical). Used to detect trigger keys.
PYNPUT_MODIFIERS: typing.Final[frozenset[str]] = frozenset(
    key.name for key in Key if key.name.startswith(("ctrl", "alt", "shift", "cmd"))
)


def convert_token(token: str, shortcut: str) -> str:
    """
    Convert a single lowercased token to its pynput representation.
    """
    canonical = KEY_ALIASES.get(token, token)
    if canonical in PYNPUT_KEY_NAMES:
        return f"<{canonical}>"
    if len(canonical) == 1:
        return canonical
    raise KeyboardShortcutParseError(f"unknown key in shortcut {shortcut!r}: {token!r}")


def to_pynput_hotkey(shortcut: QtShortcutStr) -> PyShortcutStr:
    """
    Convert a human-readable shortcut string (e.g. "Ctrl+Shift+F5", "Meta+O")
    to pynput's format (e.g. "<ctrl>+<shift>+<f5>", "<cmd>+o").

    Raises KeyboardShortcutParseError if the shortcut is empty, contains an
    unrecognized token, or has no non-modifier trigger key.
    """
    converted: list[str] = [convert_token(tok.strip().lower(), shortcut) for tok in shortcut.split("+") if tok.strip()]
    if not converted:
        raise KeyboardShortcutParseError(f"empty shortcut: {shortcut!r}")
    # A token is a trigger key if its pynput name is not a modifier.
    has_trigger = any(tok.strip("<>") not in PYNPUT_MODIFIERS for tok in converted)
    if not has_trigger:
        raise KeyboardShortcutParseError(f"shortcut has no trigger key: {shortcut!r}")
    return PyShortcutStr("+".join(converted))


class LancetShortcutSignals(QObject):
    """Qt signals emitted when a global keyboard shortcut is activated."""

    shortcut_activated = pyqtSignal(LancetShortcutEnum)


def to_pynput_shortcuts(shortcuts: dict[QtShortcutStr, LancetShortcutEnum]) -> ShortcutConversionResult:
    """Convert shortcuts to pynput format, collecting any that fail to parse."""
    result = ShortcutConversionResult()
    for shortcut, action_name in shortcuts.items():
        shortcut = QtShortcutStr(shortcut.strip())
        if not shortcut:
            continue
        try:
            result.hotkeys[to_pynput_hotkey(shortcut)] = action_name
        except KeyboardShortcutParseError as ex:
            result.failures.append(ShortcutParseFailure(action_name, shortcut, str(ex)))
            logger.warning(f"skipping shortcut {action_name.name}={shortcut!r}: {ex}")
            continue
    return result


class LancetShortcutManager:
    """Listens for global keyboard shortcuts and emits Qt signals when they are pressed."""

    def __init__(self, shortcuts: dict[PyShortcutStr, LancetShortcutEnum]) -> None:
        """Register shortcuts and start listening."""
        self.signals = LancetShortcutSignals()
        self._listener = GlobalHotKeys(self._bind_shortcuts(shortcuts))

    def start_listener(self) -> None:
        self._listener.start()
        logger.info("Started shortcut listener")

    def restart_listener(self, shortcuts: dict[PyShortcutStr, LancetShortcutEnum]) -> None:
        self.stop_listener()
        self._listener = GlobalHotKeys(self._bind_shortcuts(shortcuts))
        self.start_listener()

    def stop_listener(self) -> None:
        self._listener.stop()
        logger.info("Stopped shortcut listener")

    def _bind_shortcuts(
        self, shortcuts: dict[PyShortcutStr, LancetShortcutEnum]
    ) -> dict[PyShortcutStr, Callable[[], None]]:
        """Bind shortcut enums to signal-emitting callbacks."""
        return {
            pynput_form: functools.partial(self._on_shortcut_activated, action_name)
            for pynput_form, action_name in shortcuts.items()
        }

    def _on_shortcut_activated(self, action_name: LancetShortcutEnum) -> None:
        """Emit the shortcut_activated signal for the given action."""
        q_emit(self.signals.shortcut_activated, action_name)
