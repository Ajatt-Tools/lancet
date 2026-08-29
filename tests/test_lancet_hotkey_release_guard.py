# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import typing

from lancet.keyboard_shortcuts.hotkey import SiblingAwareHotKey
from tests.helpers import ALT, KEY_O, KEY_P, Counter


class HotkeyAndCounter(typing.NamedTuple):
    """A latched hotkey paired with the callback counter it invokes."""

    hotkey: SiblingAwareHotKey
    counter: Counter


def make_satisfied_alt_o_hotkey() -> HotkeyAndCounter:
    """Build an <alt>+o SiblingAwareHotKey and drive it to the activated/latched state."""
    counter = Counter()
    hotkey = SiblingAwareHotKey({ALT, KEY_O}, counter)
    hotkey.update_state(ALT)
    hotkey.update_state(KEY_O)
    hotkey.try_activate({ALT})
    assert counter.count == 1  # sanity: hotkey activated and latched
    return HotkeyAndCounter(hotkey=hotkey, counter=counter)


class TestLancetHotKeyReleaseGuard:
    """
    The release() guard checks membership in self._keys (via tracks()), not self._state.

    This means a "stray" release for a key that belongs to the shortcut but is no longer
    tracked as held still resets the activation latch. The two tests below verify the two
    halves of that contract:

      - Stray release of an in-_keys key resets the latch (decisive divergence test).
      - Release of a key not in _keys is a no-op (must not reset the latch).
    """

    def test_release_of_in_keys_unheld_key_resets_latch(self) -> None:
        """A stray release for an in-_keys key that is not currently tracked still resets the latch."""
        hotkey, counter = make_satisfied_alt_o_hotkey()

        # Model a stray release: directly clear KEY_O from _state without going through release(),
        # then call release(KEY_O). Under the new guard (membership in _keys), the latch must be
        # reset; under the old guard (membership in _state), it would not have been.
        hotkey._state.discard(KEY_O)
        hotkey.release(KEY_O)

        # Re-press KEY_O to drive the combo back to the satisfied state. Latch is reset, so the
        # callback must fire again.
        hotkey.update_state(KEY_O)
        hotkey.try_activate({ALT})
        assert counter.count == 2

    def test_release_of_key_not_in_keys_is_noop(self) -> None:
        """Releasing a key that is not part of the shortcut must NOT reset the latch."""
        hotkey, counter = make_satisfied_alt_o_hotkey()

        # KEY_P is not in the shortcut's key set; releasing it must not affect the latch.
        hotkey.release(KEY_P)

        # OS auto-repeat of KEY_O while still latched and combo satisfied: must not re-fire.
        hotkey.update_state(KEY_O)
        hotkey.try_activate({ALT})
        assert counter.count == 1
