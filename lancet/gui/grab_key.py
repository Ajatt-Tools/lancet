# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
import sys
from collections.abc import Sequence

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent, QKeySequence
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QLabel,
    QLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from zala.utils import qconnect


def mod_mask_qt6() -> Qt.KeyboardModifier:
    """Return a bitmask combining all supported keyboard modifiers."""
    return (
        Qt.KeyboardModifier.ControlModifier
        | Qt.KeyboardModifier.AltModifier
        | Qt.KeyboardModifier.ShiftModifier
        | Qt.KeyboardModifier.MetaModifier
    )


def forbidden_keys() -> Sequence[Qt.Key]:
    """Return the keys that should not be accepted as standalone shortcut keys."""
    return (
        Qt.Key.Key_Shift,
        Qt.Key.Key_Alt,
        Qt.Key.Key_Control,
        Qt.Key.Key_Meta,
    )


def modifiers_allowed(modifiers: Qt.KeyboardModifier) -> bool:
    """Check whether the given modifiers consist only of allowed modifier keys."""
    return modifiers & mod_mask_qt6() == modifiers  # Qt6


def to_int(modifiers: Qt.KeyboardModifier) -> int:
    """Convert a Qt keyboard modifier flag to its integer value."""
    return int(modifiers.value)  # Qt6


class KeyPressDialog(QDialog):
    """A modal dialog that captures a key combination from the user."""

    value_accepted = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None, initial_value: str = "", *args, **kwargs) -> None:
        """Initialize the dialog with an optional initial shortcut value."""
        super().__init__(parent, *args, **kwargs)
        self._shortcut = initial_value
        self.setMinimumSize(380, 64)
        self.setWindowTitle("Grab key combination")
        self.setLayout(self._make_layout())

    @staticmethod
    def _make_layout() -> QLayout:
        """Create the dialog layout with an instruction label."""
        label = QLabel(
            "Please press the key combination you would like to assign.\n"
            "Supported modifiers: CTRL, ALT, SHIFT or META.\n"
            "Press ESC to delete the shortcut."
        )
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout = QVBoxLayout()
        layout.addWidget(label)
        return layout

    def _accept_new_shortcut(self, value: str) -> None:
        """Set the shortcut and close the dialog with an accepted result."""
        self.set_shortcut(value)
        self.accept()

    def set_shortcut(self, value: str) -> None:
        """Update the stored shortcut and emit the value_accepted signal."""
        self._shortcut = value
        self.value_accepted.emit(value)  # type: ignore

    def current_shortcut(self) -> str:
        """Return the currently assigned shortcut string."""
        return self._shortcut

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handle key presses: ESC clears the shortcut, valid modifier+key combos are accepted."""
        # https://stackoverflow.com/questions/35033116
        # https://doc.qt.io/qt-6/qdialog.html#keyPressEvent
        key = int(event.key())
        modifiers = event.modifiers()

        if key == Qt.Key.Key_Escape:
            self._accept_new_shortcut("")
        elif modifiers and modifiers_allowed(modifiers) and key > 0 and key not in forbidden_keys():
            self._accept_new_shortcut(QKeySequence(to_int(modifiers) + key).toString())


class ShortCutGrabButton(QPushButton):
    """A button that opens a key grab dialog when clicked and displays the assigned shortcut."""

    _placeholder = "[Not assigned]"

    def __init__(self, initial_value: str | None = None) -> None:
        """Initialize the button with an optional shortcut and connect it to the grab dialog."""
        super().__init__(initial_value or self._placeholder)
        self._dialog = KeyPressDialog(self, initial_value or "")
        qconnect(self.clicked, self._dialog.exec)
        qconnect(
            self._dialog.value_accepted,
            lambda value: self.setText(value or self._placeholder),
        )

    def set_keyboard_shortcut(self, value: str) -> None:
        """Programmatically set the keyboard shortcut."""
        self._dialog.set_shortcut(value.strip())

    def current_shortcut(self) -> str:
        """Return the currently assigned shortcut, or an empty string if none."""
        return self._dialog.current_shortcut() or ""


def detect_keypress() -> None:
    """Launch a test dialog for experimenting with keyboard shortcut capture."""
    app = QApplication(sys.argv)
    w = QDialog()
    w.setWindowTitle("Test")
    w.setLayout(layout := QVBoxLayout())
    layout.addWidget(b := ShortCutGrabButton())
    w.show()
    code: int = app.exec()
    print(f"{'Accepted' if w.result() else 'Rejected'}. Code: {code}, shortcut: \"{b.current_shortcut()}\"")
    sys.exit(code)


if __name__ == "__main__":
    detect_keypress()
