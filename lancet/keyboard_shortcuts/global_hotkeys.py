# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
from collections.abc import Callable, Sequence

from pynput.keyboard import HotKey, Key, KeyCode, Listener

from lancet.exceptions import DuplicateShortcutError
from lancet.keyboard_shortcuts.consts import PYNPUT_MODIFIERS
from lancet.keyboard_shortcuts.hotkey import HotKeyStateUpdate, SiblingAwareHotKey
from lancet.keyboard_shortcuts.types import ParsedEntry, PyShortcutStr


def build_parsed_entries(hotkeys: dict[PyShortcutStr, Callable[[], None]]) -> Sequence[ParsedEntry]:
    """Parse each shortcut string and return ParsedEntry objects."""
    return [
        ParsedEntry(
            shortcut=shortcut,
            key_set=frozenset(HotKey.parse(shortcut)),
            action=action,
        )
        for shortcut, action in hotkeys.items()
    ]


def reject_duplicate_key_sets(entries: Sequence[ParsedEntry]) -> Sequence[ParsedEntry]:
    """
    Raise DuplicateShortcutError if any two entries resolve to the same key set.

    Two shortcut strings that differ only in token order (e.g. <alt>+<shift>+o and <shift>+<alt>+o)
    are considered duplicates because pynput's HotKey.parse normalizes them to equal frozen sets.
    """
    seen: dict[frozenset[KeyCode | Key], PyShortcutStr] = {}
    for entry in entries:
        if entry.key_set in seen:
            raise DuplicateShortcutError(
                f"shortcuts {seen[entry.key_set]!r} and {entry.shortcut!r} resolve to the same key set"
            )
        seen[entry.key_set] = entry.shortcut
    return entries


def prepare_hotkeys(hotkeys: dict[PyShortcutStr, Callable[[], None]]) -> Sequence[SiblingAwareHotKey]:
    """Parse shortcut strings, reject duplicates, and build sibling-aware hotkeys."""
    entries = build_parsed_entries(hotkeys)
    reject_duplicate_key_sets(entries)
    sibling_aware_hotkeys = tuple(SiblingAwareHotKey(e.key_set, e.action) for e in entries)
    for hotkey in sibling_aware_hotkeys:
        hotkey.set_siblings(sibling_aware_hotkeys)
    return sibling_aware_hotkeys


class LancetHotKeyListener(Listener):
    """
    A keyboard listener that supports a number of global hotkeys,
    suppressing activation of less-specific hotkeys when a more-specific overlapping hotkey is satisfied.
    Raises DuplicateShortcutError at construction if any two shortcuts resolve to the same set of keys.

    This class replaces pynput.keyboard.GlobalHotKeys.
    Uses class SiblingAwareHotKey instead of pynput's HotKey.
    A two-phase per-event protocol: every hotkey's state is updated before any activation decision is made.
    """

    _hotkeys: Sequence[SiblingAwareHotKey]
    _pressed_modifiers: set[KeyCode | Key]

    def __init__(self, hotkeys: dict[PyShortcutStr, Callable[[], None]]) -> None:
        """Build sibling-aware hotkeys."""
        # Assign self._hotkeys before super().__init__ as a defensive measure
        # because the parent's _wrap() introspects self._on_press at construction time.
        self._hotkeys = prepare_hotkeys(hotkeys)
        self._pressed_modifiers = set()
        super().__init__(on_press=self._on_press, on_release=self._on_release)  # type: ignore[arg-type]

    def _canonical_pressed_modifiers(self) -> frozenset[KeyCode | Key]:
        """Return the canonical modifiers represented by the pressed physical keys."""
        return frozenset(self.canonical(key) for key in self._pressed_modifiers)

    def _try_activate_hotkeys(
        self,
        hotkeys: Sequence[SiblingAwareHotKey],
        pressed_modifiers: frozenset[KeyCode | Key],
    ) -> None:
        """Try to activate hotkeys whose held state changed on the current press."""
        for hotkey in hotkeys:
            hotkey.try_activate(pressed_modifiers)

    def _on_press(self, key: Key | KeyCode | None, injected: bool) -> None:
        """Track a real key press and activate only hotkeys with a fresh state transition."""
        if injected or key is None:
            return
        canonical = self.canonical(key)
        if canonical in PYNPUT_MODIFIERS:
            # Keep physical variants distinct so releasing one side does not erase the other.
            self._pressed_modifiers.add(key)
        # Update every state for sibling suppression, but only fresh transitions
        # may activate; auto-repeat must not revive a previously blocked chord.
        transitioned = tuple(
            hotkey for hotkey in self._hotkeys if hotkey.update_state(canonical) is HotKeyStateUpdate.changed
        )
        self._try_activate_hotkeys(transitioned, self._canonical_pressed_modifiers())

    def _on_release(self, key: Key | KeyCode | None, injected: bool) -> None:
        """Release a real key, preserving canonical modifiers until their final physical variant is released."""
        if injected or key is None:
            return
        canonical = self.canonical(key)
        self._pressed_modifiers.discard(key)
        # Left and right modifier keys share one canonical state. Do not release it
        # while another physical variant remains held.
        if canonical in self._canonical_pressed_modifiers():
            return
        for hotkey in self._hotkeys:
            hotkey.release(canonical)
