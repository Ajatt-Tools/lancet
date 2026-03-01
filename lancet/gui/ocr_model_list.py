# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
from collections.abc import Sequence

from PyQt6.QtWidgets import QGroupBox, QComboBox, QPushButton, QGridLayout, QLayout, QWidget
from zala.utils import qconnect


class EditableSelector(QComboBox):
    """
    Convenience class for making combo boxes with editable input field.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setEditable(True)


class ModelListEditor(QGroupBox):
    def __init__(self, name: str = "") -> None:
        super().__init__(name)
        self._model_names = dict()
        self.combo = EditableSelector()
        self.add_selected = QPushButton("Add current")
        self.remove_selected = QPushButton("Remove current")
        self.setLayout(self.create_layout())
        self.connect_buttons()

    def create_layout(self) -> QLayout:
        layout = QGridLayout()
        layout.addWidget(self.combo, 0, 0, 1, 2)  # row, col, row-span, col-span
        layout.addWidget(self.add_selected, 1, 0)
        layout.addWidget(self.remove_selected, 1, 1)
        return layout

    def current_text(self) -> str:
        return self.combo.currentText().strip()

    def set_current(self, model_name: str) -> None:
        self.combo.setCurrentText(model_name)

    def models_as_list(self) -> list[str]:
        items = [self.combo.itemText(index) for index in range(self.combo.count())]
        items.append(self.current_text())
        return list(dict.fromkeys(items))

    def add_items(self, model_names: Sequence[str]) -> None:
        for item in model_names:
            self.combo.addItem(item, item)

    def set_items(self, items: Sequence[str]) -> None:
        """
        Remove all previously added items and add new items.
        """
        self.combo.clear()
        self.add_items(list(dict.fromkeys(items)))

    def add_new_preset(self) -> None:
        # https://doc.qt.io/qt-6/qcombobox.html#findText
        # If not found, then add.
        if (text := self.combo.currentText().strip()) and self.combo.findText(text) == -1:
            self.combo.addItem(self.combo.currentText())

    def connect_buttons(self) -> None:
        # https://doc.qt.io/qt-6/qabstractbutton.html#clicked
        qconnect(self.add_selected.clicked, lambda: self.add_new_preset())
        qconnect(self.remove_selected.clicked, lambda: self.combo.removeItem(self.combo.currentIndex()))
