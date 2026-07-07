# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import typing

import pytest

from lancet.exceptions import DuplicateShortcutError
from lancet.keyboard_shortcuts.global_hotkeys import LancetHotKeyListener
from lancet.keyboard_shortcuts.types import PyShortcutStr
from tests.test_lancet_hotkey_tracks import Counter


class ShortcutPair(typing.NamedTuple):
    """A pair of shortcut strings that resolve to the same pynput key set."""

    first: PyShortcutStr
    second: PyShortcutStr


DUPLICATE_SHORTCUT_PAIRS: dict[str, ShortcutPair] = {
    # Identical key sets expressed in different token orders.
    "alt_shift_order": ShortcutPair(PyShortcutStr("<alt>+<shift>+o"), PyShortcutStr("<shift>+<alt>+o")),
    "ctrl_shift_order": ShortcutPair(PyShortcutStr("<ctrl>+<shift>+f"), PyShortcutStr("<shift>+<ctrl>+f")),
    "ctrl_alt_order": ShortcutPair(PyShortcutStr("<ctrl>+<alt>+p"), PyShortcutStr("<alt>+<ctrl>+p")),
}

# Pairs of shortcut strings that resolve to the same pynput key set.
# The second string differs from the first only in token order, which
# HotKey.parse normalises away.


class TestDuplicateShortcutsRejected:
    """LancetHotKeyListener must raise DuplicateShortcutError for duplicate key sets."""

    @pytest.mark.parametrize("pair", DUPLICATE_SHORTCUT_PAIRS.values(), ids=DUPLICATE_SHORTCUT_PAIRS.keys())
    def test_duplicate_raises(self, pair: ShortcutPair) -> None:
        """Two shortcuts resolving to the same key set raise DuplicateShortcutError."""
        counter_a, counter_b = Counter(), Counter()
        with pytest.raises(DuplicateShortcutError):
            LancetHotKeyListener({pair.first: counter_a, pair.second: counter_b})
