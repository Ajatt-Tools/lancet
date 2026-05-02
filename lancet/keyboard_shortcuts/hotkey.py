# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from collections.abc import Callable, Iterable, Sequence

from pynput.keyboard import Key, KeyCode

from lancet.exceptions import KeyboardShortcutParseError


class SiblingAwareHotKey:
    """
    A hotkey class that defers activation when a more-specific sibling hotkey is also satisfied.
    """

    _keys: frozenset[KeyCode | Key]
    _state: set[KeyCode | Key]
    _on_activate: Callable[[], None]
    _activation_latched: bool
    _more_specific_siblings: Sequence["SiblingAwareHotKey"]

    def __init__(self, keys: Iterable[KeyCode | Key], on_activate: Callable[[], None]) -> None:
        self._keys = frozenset(keys)
        self._state = set()
        self._on_activate = on_activate
        self._activation_latched = False
        self._more_specific_siblings = ()

    def is_satisfied(self) -> bool:
        """True if every key in self._keys is currently held."""
        return self._state == self._keys

    def tracks(self, key: KeyCode | Key) -> bool:
        """True if key belongs to this hotkey's combination."""
        return key in self._keys

    def set_siblings(self, siblings: Sequence["SiblingAwareHotKey"]) -> None:
        """
        Record sibling hotkeys whose key set strictly contains this one's.

        Call this once after all hotkeys in the group have been constructed.
        """
        if self._more_specific_siblings:
            raise KeyboardShortcutParseError("more specific siblings already set")
        self._more_specific_siblings = tuple(
            shortcut for shortcut in siblings if shortcut is not self and shortcut._keys > self._keys
        )

    def update_state(self, key: KeyCode | Key) -> None:
        """
        Phase 1: record a key press without activating.

        The listener calls this on every registered hotkey first,
        so all states reflect the current key event before any activation decision.
        """
        if self.tracks(key):
            self._state.add(key)

    def try_activate(self) -> None:
        """
        Phase 2: fire the callback if fully held, not already latched,
        and no more-specific sibling is simultaneously satisfied.
        """
        if not self.is_satisfied() or self._activation_latched:
            return
        if any(sibling.is_satisfied() for sibling in self._more_specific_siblings):
            return
        self._activation_latched = True
        self._on_activate()

    def release(self, key: KeyCode | Key) -> None:
        """
        Remove a key from the held set and reset the one-shot activation latch.

        The guard uses self.tracks() so the latch is cleared whenever a key belonging to this shortcut is released,
        even if that key is not currently tracked as held.
        """
        if not self.tracks(key):
            return
        self._state.discard(key)
        self._activation_latched = False
