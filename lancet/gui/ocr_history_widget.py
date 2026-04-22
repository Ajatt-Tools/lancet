# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
from collections.abc import Sequence

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QGroupBox,
    QHBoxLayout,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from zala.utils import qconnect

from lancet.consts import OCR_JOIN_STR

USER_ROLE = Qt.ItemDataRole.UserRole


class OcrHistoryWidget(QGroupBox):
    """A widget displaying the OCR history list with copy, remove, and clear buttons."""

    copy_requested = pyqtSignal(str)

    def __init__(self, history_items: Sequence[str], parent: QWidget | None = None) -> None:
        """Initialize the history widget with the given history data."""
        super().__init__("OCR History", parent)

        layout = QVBoxLayout()
        self.setLayout(layout)

        self._list = QListWidget()
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._populate_list(history_items)
        layout.addWidget(self._list)

        button_row = QHBoxLayout()
        self._copy_btn = QPushButton("Copy selected")
        self._remove_btn = QPushButton("Remove selected")
        self._clear_btn = QPushButton("Clear all")
        button_row.addWidget(self._copy_btn)
        button_row.addWidget(self._remove_btn)
        button_row.addWidget(self._clear_btn)
        layout.addLayout(button_row)

        qconnect(self._copy_btn.clicked, lambda: self._copy_selected())
        qconnect(self._remove_btn.clicked, lambda: self._remove_selected())
        qconnect(self._clear_btn.clicked, lambda: self._clear_all())

    def _populate_list(self, history_items: Sequence[str]) -> None:
        self._list.clear()
        for idx, text in enumerate(history_items):
            self._list.addItem(text)
            self._list.item(idx).setData(USER_ROLE, idx)

    def as_list(self) -> list[str]:
        return [self._list.item(i).text() for i in range(self._list.count())]

    def _copy_selected(self) -> None:
        """Combine selected items into one string and emit the copy_requested signal."""
        selected_items = self._list.selectedItems()
        selected_items.sort(key=lambda item: item.data(USER_ROLE), reverse=True)
        if not selected_items:
            return
        combined = OCR_JOIN_STR.join(item.text() for item in selected_items)
        self.copy_requested.emit(combined)

    def _remove_selected(self) -> None:
        """Remove selected entries from the history and refresh the list."""
        for selected_item in reversed(self._list.selectedItems()):
            # https://doc.qt.io/archives/qt-5.15/qlistwidget.html#takeItem
            self._list.takeItem(self._list.row(selected_item))

    def _clear_all(self) -> None:
        """Clear all history entries and refresh the list."""
        self._list.clear()
