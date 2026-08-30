# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import typing
from collections.abc import Mapping
from types import MappingProxyType

from pynput.keyboard import Key

# Canonical pynput special-key names, derived from the pynput.keyboard.Key enum.
# This ensures we stay in sync with whatever pynput version is installed.
PYNPUT_KEY_NAMES: typing.Final[frozenset[str]] = frozenset(key.name for key in Key)

# Aliases: maps user/Qt spellings to canonical pynput names.
# Includes modifier mappings (Qt's "Meta" is Win/Super/Cmd, pynput calls all of them "cmd")
# and common abbreviations that Qt and users produce (e.g. "Del" instead of "Delete").
KEY_ALIASES: typing.Final[Mapping[str, str]] = MappingProxyType(
    {
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
)

MODIFIER_KEYS: typing.Final[tuple[str, ...]] = ("ctrl", "alt", "shift", "cmd")
PYNPUT_MODIFIERS: typing.Final[frozenset[Key]] = frozenset(key for key in Key if key.name.startswith(MODIFIER_KEYS))

# All pynput modifier names (canonical). Used to detect trigger keys.
PYNPUT_MODIFIER_NAMES: typing.Final[frozenset[str]] = frozenset(key.name for key in PYNPUT_MODIFIERS)
