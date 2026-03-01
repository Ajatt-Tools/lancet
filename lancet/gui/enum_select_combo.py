# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import enum

from PyQt6.QtWidgets import QComboBox, QWidget


class EnumSelectCombo(QComboBox):
    def __init__(
        self,
        initial_value: enum.Enum,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        enum_type = type(initial_value)
        for item in enum_type:
            self.addItem(item.name, item)
        self.set_current(initial_value)

    def set_current(self, value: enum.Enum) -> None:
        self.setCurrentIndex(self.findData(value))
