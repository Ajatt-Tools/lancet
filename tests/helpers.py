# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Test helpers for keyboard shortcuts and queued Qt callbacks."""

import typing
from collections.abc import Callable, Iterable

from pynput.keyboard import HotKey, Key, KeyCode
from PyQt6.QtCore import QEventLoop, Qt, QTimer
from PyQt6.QtGui import QKeySequence
from zala.utils import qconnect

from lancet.keyboard_shortcuts.consts import PYNPUT_MODIFIERS
from lancet.keyboard_shortcuts.hotkey import SiblingAwareHotKey
from lancet.keyboard_shortcuts.types import PyShortcutStr

ALT: Key = Key.alt
SHIFT: Key = Key.shift
CTRL: Key = Key.ctrl
KEY_O: KeyCode = KeyCode.from_char("o")
KEY_P: KeyCode = KeyCode.from_char("p")
QT_EVENT_LOOP_TIMEOUT_MS = 5_000


class QtShortcut(typing.NamedTuple):
    """A Qt modifier+key combination paired with the expected pynput conversion."""

    modifiers: Qt.KeyboardModifier
    key: Qt.Key
    expected_pynput: str


class Counter:
    """Callable that counts how many times it has been invoked."""

    count: int

    def __init__(self) -> None:
        self.count = 0

    def __call__(self) -> None:
        self.count += 1


def wait_for_qt_event_loop(loop: QEventLoop, timeout_ms: int = QT_EVENT_LOOP_TIMEOUT_MS) -> None:
    """Run a nested Qt loop and raise AssertionError when it exceeds its deadline."""
    timer = QTimer()
    timer.setSingleShot(True)
    qconnect(timer.timeout, loop.quit)
    timer.start(timeout_ms)
    loop.exec()
    if not timer.isActive():
        raise AssertionError(f"Qt event loop did not finish within {timeout_ms} ms")
    timer.stop()


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


def feed_press(
    hotkeys: Iterable[SiblingAwareHotKey], key: Key | KeyCode, pressed_modifiers: set[Key | KeyCode]
) -> None:
    """
    Feed a key press event to all hotkeys using the two-phase protocol used by class LancetHotKeyListener.
    """
    hotkeys = list(hotkeys)
    if key in PYNPUT_MODIFIERS:
        pressed_modifiers.add(key)
    for hotkey in hotkeys:
        hotkey.update_state(key)
    for hotkey in hotkeys:
        hotkey.try_activate(pressed_modifiers)


def feed_release(
    hotkeys: Iterable[SiblingAwareHotKey], key: Key | KeyCode, pressed_modifiers: set[Key | KeyCode]
) -> None:
    """Feed a key release event to all hotkeys."""
    pressed_modifiers.discard(key)
    for hotkey in hotkeys:
        hotkey.release(key)
