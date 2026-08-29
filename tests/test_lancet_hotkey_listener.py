# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
import typing
from collections.abc import Sequence

import pytest
from pynput.keyboard import Key as PynputKey
from pynput.keyboard import KeyCode

from lancet.keyboard_shortcuts.global_hotkeys import LancetHotKeyListener
from lancet.keyboard_shortcuts.types import PyShortcutStr
from tests.helpers import ALT, KEY_O, SHIFT, Counter


class ListenerEvent(typing.NamedTuple):
    """A single keyboard event delivered to LancetHotKeyListener, with injected flag."""

    kind: typing.Literal["press", "release"]
    key: PynputKey | KeyCode
    injected: bool = False


class ListenerIntegrationScenario(typing.NamedTuple):
    """A scenario for exercising LancetHotKeyListener._on_press/_on_release directly."""

    shortcuts: Sequence[PyShortcutStr]
    events: Sequence[ListenerEvent]
    expected_counts: Sequence[int]


def lpress(key: PynputKey | KeyCode, *, injected: bool = False) -> ListenerEvent:
    """Convenience constructor for a press ListenerEvent."""
    return ListenerEvent("press", key, injected)


def lrelease(key: PynputKey | KeyCode, *, injected: bool = False) -> ListenerEvent:
    """Convenience constructor for a release ListenerEvent."""
    return ListenerEvent("release", key, injected)


LISTENER_INTEGRATION_SCENARIOS: dict[str, ListenerIntegrationScenario] = {
    "zero_hotkeys_constructs_and_idles": ListenerIntegrationScenario(
        shortcuts=(),
        events=(lpress(ALT), lpress(KEY_O), lrelease(KEY_O), lrelease(ALT)),
        expected_counts=(),
    ),
    "more_specific_suppresses_less_specific": ListenerIntegrationScenario(
        shortcuts=(PyShortcutStr("<alt>+o"), PyShortcutStr("<shift>+<alt>+o")),
        events=(lpress(ALT), lpress(SHIFT), lpress(KEY_O)),
        expected_counts=(0, 1),
    ),
    "injected_press_ignored_non_injected_activates": ListenerIntegrationScenario(
        shortcuts=(PyShortcutStr("<alt>+o"),),
        # The injected Alt press is ignored; the real Alt + O pair activates.
        events=(lpress(ALT, injected=True), lpress(ALT), lpress(KEY_O)),
        expected_counts=(1,),
    ),
    "injected_release_does_not_reset_latch": ListenerIntegrationScenario(
        shortcuts=(PyShortcutStr("<alt>+o"),),
        # Activate with real keypresses, then send an injected release; latch must hold.
        events=(lpress(ALT), lpress(KEY_O), lrelease(KEY_O, injected=True), lpress(KEY_O)),
        expected_counts=(1,),
    ),
    "single_shortcut_blocks_incidentally_held_modifier_via_listener": ListenerIntegrationScenario(
        # Exact modifier matching rejects <alt>+o while an unrelated SHIFT is held,
        # even when no more-specific sibling is registered.
        shortcuts=(PyShortcutStr("<alt>+o"),),
        events=(lpress(SHIFT), lpress(ALT), lpress(KEY_O)),
        expected_counts=(0,),
    ),
    "released_extra_modifier_allows_activation": ListenerIntegrationScenario(
        shortcuts=(PyShortcutStr("<alt>+o"),),
        events=(lpress(SHIFT), lrelease(SHIFT), lpress(ALT), lpress(KEY_O)),
        expected_counts=(1,),
    ),
    "modifier_autorepeat_is_idempotent": ListenerIntegrationScenario(
        shortcuts=(PyShortcutStr("<shift>+<alt>+o"),),
        events=(lpress(SHIFT), lpress(SHIFT), lpress(ALT), lpress(KEY_O)),
        expected_counts=(1,),
    ),
}


class TestLancetHotKeyListenerIntegration:
    """Exercise LancetHotKeyListener._on_press/_on_release directly (no OS thread)."""

    @pytest.mark.parametrize(
        "scenario",
        LISTENER_INTEGRATION_SCENARIOS.values(),
        ids=LISTENER_INTEGRATION_SCENARIOS.keys(),
    )
    def test_listener_integration(self, scenario: ListenerIntegrationScenario) -> None:
        """Drive the listener's internal callbacks and verify activation counts."""
        counters = [Counter() for _ in scenario.shortcuts]
        listener = LancetHotKeyListener(dict(zip(scenario.shortcuts, counters)))

        for event in scenario.events:
            canonical_key = listener.canonical(event.key)
            if event.kind == "press":
                listener._on_press(canonical_key, event.injected)
            else:
                listener._on_release(canonical_key, event.injected)

        actual = tuple(c.count for c in counters)
        assert actual == scenario.expected_counts
