# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
from collections.abc import Callable, Iterable, Sequence

from pynput.keyboard import HotKey, KeyCode, Key, Listener

from lancet.exceptions import DuplicateShortcutError
from lancet.keyboard_shortcuts.hotkey import SiblingAwareHotKey
from lancet.keyboard_shortcuts.types import PyShortcutStr, ParsedEntry


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

    def __init__(self, hotkeys: dict[PyShortcutStr, Callable[[], None]]) -> None:
        """Build sibling-aware hotkeys."""
        # Assign self._hotkeys before super().__init__ as a defensive measure
        # because the parent's _wrap() introspects self._on_press at construction time.
        self._hotkeys = prepare_hotkeys(hotkeys)
        super().__init__(on_press=self._on_press, on_release=self._on_release)  # type: ignore[arg-type]

    def _on_press(self, key: Key | KeyCode | None, injected: bool) -> None:
        """Update every hotkey's state, then ask each to activate if eligible."""
        if injected or key is None:
            return
        canonical = self.canonical(key)
        for hotkey in self._hotkeys:
            hotkey.update_state(canonical)
        for hotkey in self._hotkeys:
            hotkey.try_activate()

    def _on_release(self, key: Key | KeyCode | None, injected: bool) -> None:
        """Forward releases to every hotkey so per-combo activation latches reset."""
        if injected or key is None:
            return
        canonical = self.canonical(key)
        for hotkey in self._hotkeys:
            hotkey.release(canonical)
