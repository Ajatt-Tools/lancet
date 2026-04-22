# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QColorDialog, QHBoxLayout, QPushButton, QWidget
from zala.utils import qconnect

from lancet.gui.line_edit import ColorEdit


def color_to_hex_argb(color: QColor) -> str:
    """Return the color as a hex ARGB string."""
    return color.name(QColor.NameFormat.HexArgb).upper()


class ColorEditPicker(QWidget):
    def __init__(self, initial_color: str, parent=None) -> None:
        super().__init__(parent)
        # Create members
        self._edit = ColorEdit()
        self.set_color(initial_color)
        # Create layout
        self.setLayout(layout := QHBoxLayout())
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._edit)
        layout.addWidget(b := QPushButton("Pick"))
        b.setMinimumSize(32, 16)
        b.setBaseSize(32, 22)
        qconnect(b.clicked, lambda: self.choose_color())

    def choose_color(self) -> None:
        color = QColorDialog.getColor(
            initial=QColor.fromString(self._edit.text() or "black"),
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
