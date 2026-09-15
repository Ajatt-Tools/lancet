# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from PyQt6.QtCore import QRegularExpression
from PyQt6.QtGui import QRegularExpressionValidator
from PyQt6.QtWidgets import QLineEdit, QWidget


class MonoSpaceLineEdit(QLineEdit):
    """Compact monospace line edit used for technical preference values."""

    font_size: int = 14
    # Compact rows keep the preferences dialog dense without changing font size.
    min_height: int = 24

    def __init__(self, text: str = "", *, parent: QWidget | None = None) -> None:
        """Create a compact line edit with optional initial text and parent widget."""
        super().__init__(text, parent)
        font = self.font()
        font.setFamilies(
            (
                "Noto Mono",
                "Noto Sans Mono",
                "DejaVu Sans Mono",
                "Droid Sans Mono",
                "Liberation Mono",
                "Courier New",
                "Courier",
                "Lucida",
                "Monaco",
                "Monospace",
            )
        )
        font.setPixelSize(self.font_size)
        self.setMinimumHeight(self.min_height)
        self.setFont(font)


class StripLineEdit(MonoSpaceLineEdit):
    """A monospace line edit whose saved value excludes surrounding whitespace."""

    def text_stripped(self) -> str:
        """Return the current text without leading or trailing whitespace."""
        return self.text().strip()


class ColorEdit(MonoSpaceLineEdit):
    """Monospace line edit restricted to ARGB-style color text."""

    font_size: int = 14
    min_height: int = 24

    def __init__(self, text: str = "", *, parent: QWidget | None = None) -> None:
        """Create a color-constrained compact line edit."""
        super().__init__(text, parent=parent)
        color_regex = QRegularExpression(r"^#?\w+$")  # OR stricter: r"^#?[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?$"
        color_validator = QRegularExpressionValidator(color_regex, self)
        self.setValidator(color_validator)
        self.setPlaceholderText("ARGB color code")
