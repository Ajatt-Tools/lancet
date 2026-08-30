# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import typing

import pytest
from pynput.keyboard import Key as PynputKey
from pynput.keyboard import KeyCode

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


class ReleaseGuardScenario(typing.NamedTuple):
    """A released key, optional held-state divergence, and expected activation count."""

    released_key: PynputKey | KeyCode
    discard_trigger_before_release: bool
    expected_count: int


RELEASE_GUARD_SCENARIOS: dict[str, ReleaseGuardScenario] = {
    "tracked_unheld_key_resets_latch": ReleaseGuardScenario(KEY_O, True, 2),
    "untracked_key_preserves_latch": ReleaseGuardScenario(KEY_P, False, 1),
}


class TestLancetHotKeyReleaseGuard:
    """
    The release() guard checks membership in self._keys (via tracks()), not self._state.

    This means a "stray" release for a key that belongs to the shortcut but is no longer
    tracked as held still resets the activation latch. The two scenarios below verify the two
    halves of that contract:

      - Stray release of an in-_keys key resets the latch (decisive divergence test).
      - Release of a key not in _keys is a no-op (must not reset the latch).
    """

    @pytest.mark.parametrize("scenario", RELEASE_GUARD_SCENARIOS.values(), ids=RELEASE_GUARD_SCENARIOS.keys())
    def test_release_guard(self, scenario: ReleaseGuardScenario) -> None:
        """Tracked releases reset the latch while untracked releases leave it unchanged."""
        hotkey, counter = make_satisfied_alt_o_hotkey()

        if scenario.discard_trigger_before_release:
            # Create the decisive divergence: KEY_O belongs to the shortcut but is absent from held state.
            hotkey._state.discard(KEY_O)
        hotkey.release(scenario.released_key)
        # Re-pressing KEY_O either activates after a tracked release or models auto-repeat
        # while the latch remains set after an unrelated release.
        hotkey.update_state(KEY_O)
        hotkey.try_activate({ALT})
        assert counter.count == scenario.expected_count
