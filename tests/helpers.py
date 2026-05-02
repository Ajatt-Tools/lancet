# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Test helpers for keyboard-shortcut conversion and overlap-suppression tests."""

import typing
from collections.abc import Callable, Iterable

from pynput.keyboard import HotKey, Key, KeyCode
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence

from lancet.keyboard_shortcuts.hotkey import SiblingAwareHotKey
from lancet.keyboard_shortcuts.types import PyShortcutStr


class QtShortcut(typing.NamedTuple):
    """A Qt modifier+key combination paired with the expected pynput conversion."""

    modifiers: Qt.KeyboardModifier
    key: Qt.Key
    expected_pynput: str


def qt_shortcut_to_string(shortcut: QtShortcut) -> str:
    """Render a QtShortcut to its QKeySequence.toString() form, as the grab dialog does."""
    return QKeySequence(int(shortcut.modifiers.value) + shortcut.key).toString()


def make_lancet_hotkey(shortcut: str, callback: Callable[[], None]) -> SiblingAwareHotKey:
    """Build a SiblingAwareHotKey from a pynput format shortcut string (e.g. <alt>+o)."""
    return SiblingAwareHotKey(HotKey.parse(PyShortcutStr(shortcut)), callback)


def wire_siblings(hotkeys: Iterable[SiblingAwareHotKey]) -> None:
    """Mirror the listener's wire up step so each hotkey knows its more specific siblings."""
    hotkeys = list(hotkeys)
    for hotkey in hotkeys:
        hotkey.set_siblings(hotkeys)


def feed_press(hotkeys: Iterable[SiblingAwareHotKey], key: Key | KeyCode) -> None:
    """
    Feed a key press event to all hotkeys using the two-phase protocol used by class LancetHotKeyListener.
    """
    hotkeys = list(hotkeys)
    for hotkey in hotkeys:
        hotkey.update_state(key)
    for hotkey in hotkeys:
        hotkey.try_activate()


def feed_release(hotkeys: Iterable[SiblingAwareHotKey], key: Key | KeyCode) -> None:
    """Feed a key release event to all hotkeys."""
    for hotkey in hotkeys:
        hotkey.release(key)
