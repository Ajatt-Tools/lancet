# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
import typing

import pytest
from pynput.keyboard import Key as PynputKey
from pynput.keyboard import KeyCode

from lancet.keyboard_shortcuts.hotkey import SiblingAwareHotKey
from tests.helpers import ALT, CTRL, KEY_O, KEY_P, SHIFT, Counter


class TracksCase(typing.NamedTuple):
    """A tracks() membership probe at a specified held-state phase."""

    key: PynputKey | KeyCode
    expected: bool
    held_state: typing.Literal["initial", "pressed", "released"] = "initial"


TRACKS_CASES: dict[str, TracksCase] = {
    "modifier_in_shortcut_is_tracked": TracksCase(ALT, True),
    "trigger_in_shortcut_is_tracked": TracksCase(KEY_O, True),
    "key_not_in_shortcut_is_not_tracked": TracksCase(KEY_P, False),
    "unrelated_modifier_is_not_tracked": TracksCase(SHIFT, False),
    "unrelated_modifier_ctrl_is_not_tracked": TracksCase(CTRL, False),
    "tracked_key_after_press": TracksCase(ALT, True, "pressed"),
    "untracked_key_after_press": TracksCase(KEY_P, False, "pressed"),
    "tracked_key_after_release": TracksCase(ALT, True, "released"),
    "untracked_key_after_release": TracksCase(KEY_P, False, "released"),
}


class TestLancetHotKeyTracks:
    """Verify the tracks() predicate reflects membership in the hotkey's key set."""

    @pytest.mark.parametrize("case", TRACKS_CASES.values(), ids=TRACKS_CASES.keys())
    def test_tracks_reflects_key_set_membership(self, case: TracksCase) -> None:
        """Membership remains tied to the configured key set through presses and releases."""
        hotkey = SiblingAwareHotKey({ALT, KEY_O}, Counter())
        if case.held_state != "initial":
            hotkey.update_state(ALT)
        if case.held_state == "released":
            hotkey.release(ALT)
        assert hotkey.tracks(case.key) == case.expected
