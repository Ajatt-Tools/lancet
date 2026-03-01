# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
import sys
from collections.abc import Sequence

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent, QKeySequence
from PyQt6.QtWidgets import QDialog, QWidget, QLayout, QLabel, QVBoxLayout, QPushButton, QApplication
from zala.utils import qconnect


def mod_mask_qt6() -> Qt.KeyboardModifier:
    return (
        Qt.KeyboardModifier.ControlModifier
        | Qt.KeyboardModifier.AltModifier
        | Qt.KeyboardModifier.ShiftModifier
        | Qt.KeyboardModifier.MetaModifier
    )


def forbidden_keys() -> Sequence[Qt.Key]:
    return (
        Qt.Key.Key_Shift,
        Qt.Key.Key_Alt,
        Qt.Key.Key_Control,
        Qt.Key.Key_Meta,
    )


def modifiers_allowed(modifiers: Qt.KeyboardModifier) -> bool:
    return modifiers & mod_mask_qt6() == modifiers  # Qt6


def to_int(modifiers: Qt.KeyboardModifier) -> int:
    return int(modifiers.value)  # Qt6


class KeyPressDialog(QDialog):
    value_accepted = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None, initial_value: str = "", *args, **kwargs) -> None:
        super().__init__(parent, *args, **kwargs)
        self._shortcut = initial_value
        self.setMinimumSize(380, 64)
        self.setWindowTitle("Grab key combination")
        self.setLayout(self._make_layout())

    @staticmethod
    def _make_layout() -> QLayout:
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
        self.set_shortcut(value)
        self.accept()

    def set_shortcut(self, value: str) -> None:
        self._shortcut = value
        self.value_accepted.emit(value)  # type: ignore

    def current_shortcut(self) -> str:
        return self._shortcut

    def keyPressEvent(self, event: QKeyEvent) -> None:
        # https://stackoverflow.com/questions/35033116
        # https://doc.qt.io/qt-6/qdialog.html#keyPressEvent
        key = int(event.key())
        modifiers = event.modifiers()

        if key == Qt.Key.Key_Escape:
            self._accept_new_shortcut("")
        elif modifiers and modifiers_allowed(modifiers) and key > 0 and key not in forbidden_keys():
            self._accept_new_shortcut(QKeySequence(to_int(modifiers) + key).toString())


class ShortCutGrabButton(QPushButton):
    _placeholder = "[Not assigned]"

    def __init__(self, initial_value: str | None = None) -> None:
        super().__init__(initial_value or self._placeholder)
        self._dialog = KeyPressDialog(self, initial_value or "")
        qconnect(self.clicked, self._dialog.exec)
        qconnect(
            self._dialog.value_accepted,
            lambda value: self.setText(value or self._placeholder),
        )

    def set_keyboard_shortcut(self, value: str) -> None:
        self._dialog.set_shortcut(value.strip())

    def current_shortcut(self) -> str:
        return self._dialog.current_shortcut() or ""


def detect_keypress() -> None:
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
