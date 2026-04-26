# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import pathlib

from loguru import logger
from PyQt6.QtWidgets import QDialog

from lancet.consts import GEOMETRY_FILE_PATH


class SaveAndRestoreGeomDialog(QDialog):
    _name: str = "dialog"
    _geom_file: pathlib.Path = GEOMETRY_FILE_PATH

    @property
    def name(self) -> str:
        return self._name

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._restore_geometry()

    def exec(self) -> int:
        self._restore_geometry()
        return super().exec()

    def reject(self) -> None:
        """Save geometry and reject the dialog."""
        self._save_geometry()
        return super().reject()

    def accept(self) -> None:
        """Save geometry and accept the dialog."""
        self._save_geometry()
        return super().accept()

    def _save_geometry(self) -> None:
        """Save the dialog's position and size to QSettings."""
        try:
            self._geom_file.parent.mkdir(exist_ok=True, parents=True)
            self._geom_file.write_bytes(self.saveGeometry())
        except OSError as e:
            logger.error(f"can't save geometry: {e}")

    def _restore_geometry(self) -> None:
        """Restore the dialog's position and size from QSettings."""
        try:
            geometry = self._geom_file.read_bytes()
        except OSError:
            return
        else:
            if geometry:
                self.restoreGeometry(geometry)
