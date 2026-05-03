# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
import typing
from contextlib import contextmanager

from lancet.exceptions import LancetException


class DialogRegistry:
    """
    Bookkeeping for the set of dialog names that are currently open.
    Used by OpenDialogs to guard against:
    (a) opening two dialogs with the same name simultaneously,
    (b) global hotkeys firing while a dialog is on screen.
    """

    _names: set[str]

    def __init__(self) -> None:
        self._names = set()

    def is_locked(self) -> bool:
        """Return True if any dialog is currently registered as open."""
        return bool(self._names)

    def disown_if_present(self, name: str) -> None:
        """Remove 'name' from the registry. Idempotent: safe to call when absent."""
        self._names.discard(name)

    @contextmanager
    def acquire(self, name: str) -> typing.Generator[typing.Self]:
        """
        Register 'name' for the duration of the with block.

        Raises LancetException if 'name' is already registered.
        Releases the registration on block exit, including on exceptions.
        Tolerates the registration having already been cleared (e.g. by a Qt finished signal callback firing first).
        """
        if name in self._names:
            raise LancetException(f"already locked: {name}")
        self._names.add(name)
        try:
            yield self
        finally:
            self.disown_if_present(name)
