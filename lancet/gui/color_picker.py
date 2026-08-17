# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QColorDialog, QHBoxLayout, QPushButton, QWidget
from zala.utils import q_emit, qconnect

from lancet.gui.line_edit import ColorEdit

DEFAULT_COLOR = "black"


def color_to_hex_argb(color: QColor) -> str:
    """Return the color as a hex ARGB string."""
    return color.name(QColor.NameFormat.HexArgb).upper()


class ColorEditPicker(QWidget):
    """A line edit paired with a color-pick button that emits a color_changed signal."""

    color_changed = pyqtSignal(str)

    def __init__(self, initial_color: str, parent: QWidget | None = None) -> None:
        """Create the edit and pick button, wiring the color_changed signal."""
        super().__init__(parent)
        # Create members
        self._edit = ColorEdit()
        self.set_color(initial_color or DEFAULT_COLOR)
        # Create layout
        self.setLayout(layout := QHBoxLayout())
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._edit)
        layout.addWidget(b := QPushButton("Pick"))
        b.setMinimumSize(32, 16)
        b.setBaseSize(32, 22)
        # bool checked is passed to the slot.
        # https://doc.qt.io/qt-6/qabstractbutton.html#clicked
        qconnect(b.clicked, lambda: self.choose_color())
        # https://doc.qt.io/qt-6/qlineedit.html#textChanged
        qconnect(self._edit.textChanged, lambda text: q_emit(self.color_changed, text))

    def choose_color(self) -> None:
        """Open a color dialog and update the edit with the selected color."""
        color = QColorDialog.getColor(
            initial=QColor.fromString(self._edit.text() or DEFAULT_COLOR),
            parent=self,
            title="Select color",
            options=QColorDialog.ColorDialogOption.ShowAlphaChannel,
        )
        if color.isValid():
            self._edit.setText(color_to_hex_argb(color))

    def set_color(self, hex_color: str) -> None:
        """Set the color from a hex ARGB string."""
        self._edit.setText(hex_color.upper())

    def color_hex(self) -> str:
        """Return the current color as a hex ARGB string."""
        return self._edit.text().upper()
