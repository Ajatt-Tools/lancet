# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
import pathlib

from PyQt6.QtWidgets import QFileDialog, QHBoxLayout, QLineEdit, QPushButton, QWidget
from zala.utils import qconnect

from lancet.find_executable import HARDCODED_PATHS


def best_bin_directory() -> str:
    """Return the first existing hardcoded bin directory, or the user's home directory as a fallback."""
    for bin_path in HARDCODED_PATHS:
        if bin_path.is_dir():
            return str(bin_path.resolve())
    return str(pathlib.Path.home())


class LancetFilePicker(QWidget):
    """A QLineEdit with an adjacent Browse button. Clicking Browse opens a
    QFileDialog; on accept the selected path is written into the line edit."""

    _spacing: int = 8

    def __init__(self, parent: QWidget | None = None) -> None:
        """Create the line edit and Browse button with default dialog title and filter."""
        super().__init__(parent)
        self._dialog_title = "Select file"
        self._dialog_filter = "All files (*)"
        self._path_edit = QLineEdit()
        self._browse_button = QPushButton("Browse…")
        self._init_ui()

    def _init_ui(self) -> None:
        """Lay out the line edit and browse button, and wire the button's click signal."""
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(self._spacing)
        layout.addWidget(self._path_edit, stretch=1)
        layout.addWidget(self._browse_button, stretch=0)
        self.setLayout(layout)

        # bool checked is passed to the slot.
        # https://doc.qt.io/qt-6/qabstractbutton.html#clicked
        qconnect(self._browse_button.clicked, lambda: self._on_browse())

    def get_file_path(self) -> str:
        """Return the current text in the line edit, stripped of whitespace."""
        return self._path_edit.text().strip()

    def set_file_path(self, file_path: str) -> None:
        """Set the text in the line edit."""
        self._path_edit.setText(file_path.strip())

    def set_placeholder(self, placeholder: str) -> None:
        """Set placeholder text shown when the line edit is empty."""
        self._path_edit.setPlaceholderText(placeholder.strip())

    def set_tooltip(self, tooltip: str) -> None:
        """Set tooltip on the line edit."""
        self._path_edit.setToolTip(tooltip.strip())

    def set_dialog_title(self, title: str) -> None:
        """Set the title for the file dialog."""
        self._dialog_title = title.strip()

    def set_dialog_filter(self, filter_str: str) -> None:
        """Set the file filter for the file dialog (e.g. 'Executables (*.exe)')."""
        self._dialog_filter = filter_str.strip()

    def _on_browse(self) -> None:
        """Open a file dialog and update the line edit with the selected path."""
        file_path, _selected_filter = QFileDialog.getOpenFileName(
            parent=self,
            caption=self._dialog_title,
            directory=self.get_file_path() or best_bin_directory(),
            filter=self._dialog_filter,
        )
        if file_path:
            self.set_file_path(file_path)
