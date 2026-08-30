# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
import typing
from collections.abc import Sequence

import pytest
from pynput.keyboard import Key as PynputKey
from pynput.keyboard import KeyCode

from lancet.keyboard_shortcuts.types import PyShortcutStr
from tests.helpers import (
    ALT,
    CTRL,
    KEY_O,
    KEY_P,
    SHIFT,
    Counter,
    feed_press,
    feed_release,
    make_lancet_hotkey,
    wire_siblings,
)


class HotKeyEvent(typing.NamedTuple):
    """A single keyboard event in an overlap-suppression scenario."""

    kind: typing.Literal["press", "release"]
    key: PynputKey | KeyCode


class OverlapScenario(typing.NamedTuple):
    """A complete overlap-suppression scenario: shortcuts, events, expected counts."""

    shortcuts: Sequence[PyShortcutStr]
    events: Sequence[HotKeyEvent]
    expected_counts: Sequence[int]


def press(key: PynputKey | KeyCode) -> HotKeyEvent:
    return HotKeyEvent("press", key)


def release(key: PynputKey | KeyCode) -> HotKeyEvent:
    return HotKeyEvent("release", key)


OVERLAP_SCENARIOS: dict[str, OverlapScenario] = {
    "more_specific_suppresses_less_specific": OverlapScenario(
        shortcuts=(PyShortcutStr("<alt>+o"), PyShortcutStr("<shift>+<alt>+o")),
        events=(press(ALT), press(SHIFT), press(KEY_O)),
        expected_counts=(0, 1),
    ),
    "suppression_independent_of_registration_order": OverlapScenario(
        shortcuts=(PyShortcutStr("<shift>+<alt>+o"), PyShortcutStr("<alt>+o")),
        events=(press(ALT), press(SHIFT), press(KEY_O)),
        expected_counts=(1, 0),
    ),
    "press_order_alt_shift_o": OverlapScenario(
        shortcuts=(PyShortcutStr("<alt>+o"), PyShortcutStr("<shift>+<alt>+o")),
        events=(press(ALT), press(SHIFT), press(KEY_O)),
        expected_counts=(0, 1),
    ),
    "press_order_shift_alt_o": OverlapScenario(
        shortcuts=(PyShortcutStr("<alt>+o"), PyShortcutStr("<shift>+<alt>+o")),
        events=(press(SHIFT), press(ALT), press(KEY_O)),
        expected_counts=(0, 1),
    ),
    "press_order_shift_o_alt": OverlapScenario(
        shortcuts=(PyShortcutStr("<alt>+o"), PyShortcutStr("<shift>+<alt>+o")),
        events=(press(SHIFT), press(KEY_O), press(ALT)),
        expected_counts=(0, 1),
    ),
    "less_specific_fires_alone": OverlapScenario(
        shortcuts=(PyShortcutStr("<alt>+o"), PyShortcutStr("<shift>+<alt>+o")),
        events=(press(ALT), press(KEY_O)),
        expected_counts=(1, 0),
    ),
    "independent_shortcuts_unaffected": OverlapScenario(
        shortcuts=(PyShortcutStr("<alt>+o"), PyShortcutStr("<ctrl>+p")),
        events=(
            press(CTRL),
            press(KEY_P),
            release(KEY_P),
            release(CTRL),
            press(ALT),
            press(KEY_O),
        ),
        expected_counts=(1, 1),
    ),
    "three_way_overlap_longest_wins": OverlapScenario(
        shortcuts=(
            PyShortcutStr("<ctrl>+o"),
            PyShortcutStr("<ctrl>+<alt>+o"),
            PyShortcutStr("<ctrl>+<shift>+<alt>+o"),
        ),
        events=(press(CTRL), press(SHIFT), press(ALT), press(KEY_O)),
        expected_counts=(0, 0, 1),
    ),
    "refire_after_release": OverlapScenario(
        shortcuts=(PyShortcutStr("<alt>+o"), PyShortcutStr("<shift>+<alt>+o")),
        events=(press(ALT), press(KEY_O), release(KEY_O), press(KEY_O)),
        expected_counts=(2, 0),
    ),
    "held_combo_does_not_repeat": OverlapScenario(
        shortcuts=(PyShortcutStr("<alt>+o"),),
        # OS auto-repeat: trigger key arrives twice without an intervening release.
        events=(press(ALT), press(KEY_O), press(KEY_O)),
        expected_counts=(1,),
    ),
    "modifier_release_blocks_retrigger": OverlapScenario(
        shortcuts=(PyShortcutStr("<alt>+o"),),
        events=(
            press(ALT),
            press(KEY_O),
            release(ALT),
            release(KEY_O),
            press(KEY_O),  # Without Alt held, combo not satisfied.
        ),
        expected_counts=(1,),
    ),
    "release_of_unpressed_key_is_noop": OverlapScenario(
        # Releasing a key that was never pressed must not affect state or latch.
        shortcuts=(PyShortcutStr("<alt>+o"),),
        events=(press(ALT), press(KEY_O), release(KEY_P), press(KEY_O)),
        expected_counts=(1,),
    ),
    "unrelated_key_release_does_not_reset_latch": OverlapScenario(
        # Releasing a key that is not part of the shortcut must not reset the
        # activation latch, so a subsequent press of the trigger while all
        # shortcut keys are still held does not re-fire.
        shortcuts=(PyShortcutStr("<alt>+o"),),
        events=(
            press(ALT),
            press(KEY_O),  # activates; latch set
            press(KEY_P),  # unrelated key — no effect on latch
            release(KEY_P),  # unrelated release — must NOT reset latch
            press(KEY_O),  # OS auto-repeat while latch is held; must not re-fire
        ),
        expected_counts=(1,),
    ),
    "release_of_unheld_in_keys_key_does_not_block_refire": OverlapScenario(
        # Integration-level sanity check for the release() guard: a duplicate
        # release for a key that belongs to the shortcut but is no longer held
        # must leave the hotkey ready to re-activate after a fresh press cycle.
        shortcuts=(PyShortcutStr("<alt>+o"),),
        events=(
            press(ALT),
            press(KEY_O),  # activates (count=1); latch set
            release(KEY_O),  # KEY_O in _keys and held → latch reset
            release(KEY_O),  # duplicate release: KEY_O in _keys but NOT held → still latch reset
            press(KEY_O),  # combo satisfied again → re-activates (count=2)
        ),
        expected_counts=(2,),
    ),
    "single_shortcut_blocks_incidentally_held_modifier": OverlapScenario(
        # Exact modifier matching rejects Alt+O while an unrelated Shift is held.
        shortcuts=(PyShortcutStr("<alt>+o"),),
        events=(press(SHIFT), press(ALT), press(KEY_O)),
        expected_counts=(0,),
    ),
    "single_shortcut_allows_incidentally_held_non_modifier": OverlapScenario(
        # Exact matching applies only to modifiers; unrelated trigger keys do not
        # change the configured modifier set and therefore must not block Alt+O.
        shortcuts=(PyShortcutStr("<alt>+o"),),
        events=(press(ALT), press(KEY_P), press(KEY_O)),
        expected_counts=(1,),
    ),
    "sibling_registration_redirects_activation_to_more_specific": OverlapScenario(
        # Paired with the scenario above: same press sequence, but now <shift>+<alt>+o
        # IS registered. The incidentally-held SHIFT now matters — the more-specific
        # shortcut wins, and <alt>+o is correctly suppressed. This pair documents the
        # exact contract: registration controls suppression.
        shortcuts=(PyShortcutStr("<alt>+o"), PyShortcutStr("<shift>+<alt>+o")),
        events=(press(SHIFT), press(ALT), press(KEY_O)),
        expected_counts=(0, 1),
    ),
}


class TestOverlappingShortcuts:
    """Verify that more-specific shortcuts suppress activation of less-specific overlapping ones."""

    @pytest.mark.parametrize("scenario", OVERLAP_SCENARIOS.values(), ids=OVERLAP_SCENARIOS.keys())
    def test_overlap_scenario(self, scenario: OverlapScenario) -> None:
        """Drive each scenario through LancetHotKey and verify activation counts per shortcut."""
        counters = [Counter() for _ in scenario.shortcuts]
        hotkeys = [make_lancet_hotkey(s, c) for s, c in zip(scenario.shortcuts, counters)]
        wire_siblings(hotkeys)
        pressed_modifiers: set[PynputKey | KeyCode] = set()
        for event in scenario.events:
            if event.kind == "press":
                feed_press(hotkeys, event.key, pressed_modifiers)
            else:
                feed_release(hotkeys, event.key, pressed_modifiers)

        actual = tuple(c.count for c in counters)
        assert actual == scenario.expected_counts
