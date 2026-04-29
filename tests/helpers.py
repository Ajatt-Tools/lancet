# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Test helpers for keyboard-shortcut conversion tests."""

import typing

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence


class QtShortcut(typing.NamedTuple):
    """A Qt modifier+key combination paired with the expected pynput conversion."""

    modifiers: Qt.KeyboardModifier
    key: Qt.Key
    expected_pynput: str


def qt_shortcut_to_string(shortcut: QtShortcut) -> str:
    """Render a QtShortcut to its QKeySequence.toString() form, as the grab dialog does."""
    return QKeySequence(int(shortcut.modifiers.value) + shortcut.key).toString()
