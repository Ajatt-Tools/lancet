# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
import enum
import functools

from PyQt6.QtCore import QObject, pyqtSignal
from pynput.keyboard import GlobalHotKeys
from zala.utils import q_emit

# Modifier names (case-insensitive) that pynput expects wrapped in angle brackets.
_MODIFIERS = frozenset(
    {
        "alt",
        "alt_l",
        "alt_r",
        "ctrl",
        "ctrl_l",
        "ctrl_r",
        "shift",
        "shift_l",
        "shift_r",
        "cmd",
        "cmd_l",
        "cmd_r",
        "super",
    }
)


def to_pynput_hotkey(shortcut: str) -> str:
    """
    Convert a human-readable shortcut string (e.g. "Alt+O")
    to pynput's format (e.g. "<alt>+o").
    """
    parts = [part.strip().lower() for part in shortcut.strip().split("+")]
    parts = [(f"<{part}>" if part in _MODIFIERS else part) for part in parts if part]
    return "+".join(parts)


class LancetShortcutEnum(enum.Enum):
    ocr_shortcut = enum.auto()
    screenshot_shortcut = enum.auto()


class LancetShortcutSignals(QObject):
    shortcut_activated = pyqtSignal(LancetShortcutEnum)


type KeyboardShortcut = str


class LancetShortcutManager(GlobalHotKeys):
    def __init__(self, keyboard_shortcuts: dict[LancetShortcutEnum, KeyboardShortcut], *args, **kwargs) -> None:
        hotkeys_dict = {
            to_pynput_hotkey(shortcut): functools.partial(self.on_shortcut_activated, action_name)
            for action_name, shortcut in keyboard_shortcuts.items()
        }
        super().__init__(hotkeys_dict, *args, **kwargs)
        self.signals = LancetShortcutSignals()

    def on_shortcut_activated(self, action_name: LancetShortcutEnum):
        q_emit(self.signals.shortcut_activated, action_name)
