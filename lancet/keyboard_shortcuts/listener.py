# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
import functools
from collections.abc import Callable, Sequence

from loguru import logger
from PyQt6.QtCore import QObject, pyqtSignal
from zala.utils import q_emit

from lancet.actions import LancetAction
from lancet.exceptions import KeyboardShortcutParseError
from lancet.keyboard_shortcuts.consts import (
    KEY_ALIASES,
    PYNPUT_KEY_NAMES,
    PYNPUT_MODIFIER_NAMES,
)
from lancet.keyboard_shortcuts.global_hotkeys import LancetHotKeyListener
from lancet.keyboard_shortcuts.types import (
    PyShortcutStr,
    QtShortcutStr,
    ShortcutConversionResult,
    ShortcutParseFailure,
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
    converted: Sequence[str] = [
        convert_token(tok.strip().lower(), shortcut) for tok in shortcut.split("+") if tok.strip()
    ]
    if not converted:
        raise KeyboardShortcutParseError(f"empty shortcut: {shortcut!r}")
    # A token is a trigger key if its pynput name is not a modifier.
    has_trigger = any(tok.strip("<>") not in PYNPUT_MODIFIER_NAMES for tok in converted)
    if not has_trigger:
        raise KeyboardShortcutParseError(f"shortcut has no trigger key: {shortcut!r}")
    return PyShortcutStr("+".join(converted))


class LancetShortcutSignals(QObject):
    """Qt signals emitted when a global keyboard shortcut is activated."""

    shortcut_activated = pyqtSignal(LancetAction)


def to_pynput_shortcuts(shortcuts: dict[QtShortcutStr, LancetAction]) -> ShortcutConversionResult:
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

    def __init__(self, shortcuts: dict[PyShortcutStr, LancetAction]) -> None:
        """Register shortcuts and start listening."""
        self.signals = LancetShortcutSignals()
        self._listener = LancetHotKeyListener(self._bind_shortcuts(shortcuts))

    def start_listener(self) -> None:
        """Start listening for keyboard shortcuts in a background thread."""
        self._listener.start()
        logger.info("Started shortcut listener")

    def restart_listener(self, shortcuts: dict[PyShortcutStr, LancetAction]) -> None:
        """Stop the current listener and start a new one with updated shortcuts."""
        self.stop_listener()
        self._listener = LancetHotKeyListener(self._bind_shortcuts(shortcuts))
        self.start_listener()

    def stop_listener(self) -> None:
        """Stop listening for keyboard shortcuts."""
        self._listener.stop()
        logger.info("Stopped shortcut listener")

    def _bind_shortcuts(self, shortcuts: dict[PyShortcutStr, LancetAction]) -> dict[PyShortcutStr, Callable[[], None]]:
        """Bind shortcut enums to signal-emitting callbacks."""
        return {
            pynput_form: functools.partial(self._on_shortcut_activated, action_name)
            for pynput_form, action_name in shortcuts.items()
        }

    def _on_shortcut_activated(self, action_name: LancetAction) -> None:
        """Emit the shortcut_activated signal for the given action."""
        q_emit(self.signals.shortcut_activated, action_name)
