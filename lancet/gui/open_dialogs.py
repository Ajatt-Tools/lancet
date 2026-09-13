# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from contextlib import contextmanager
from collections.abc import Generator

from zala.utils import qconnect

from lancet.gui.dialog_registry import DialogRegistry
from lancet.gui.geom_dialog import SaveAndRestoreGeomDialog


class OpenDialogs:
    """Qt-aware wrapper that ties dialog lifetime to a DialogRegistry entry."""

    _registry: DialogRegistry

    def __init__(self) -> None:
        """Initialize the dialog registry."""
        self._registry = DialogRegistry()

    def is_locked(self) -> bool:
        """Return True when at least one dialog is currently open."""
        return self._registry.is_locked()

    @contextmanager
    def lock[D: SaveAndRestoreGeomDialog](self, dialog: D) -> Generator[D]:
        with self._registry.acquire(dialog.name):
            # The dialog's result code is passed to the slot:
            # https://doc.qt.io/qt-6/qdialog.html#finished
            # Wiring 'finished' to disown_if_present clears the registry entry as soon as the dialog closes.
            qconnect(dialog.finished, lambda exit_code: self._registry.disown_if_present(dialog.name))
            yield dialog
