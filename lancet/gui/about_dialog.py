# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
import sys

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QLabel,
    QVBoxLayout,
    QWidget,
    QApplication,
    QGridLayout,
    QDialogButtonBox,
)
from zala.utils import qconnect

from lancet.consts import APP_LOGO_PATH, APP_NAME, GITHUB_URL, CHAT_URL


def _linked(url: str, label: str) -> str:
    return f'<a href="{url}">{label or url}</a>'


class AppIconLabel(QLabel):
    _size: int = 128

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        pixmap = QPixmap(str(APP_LOGO_PATH)).scaled(
            self._size,
            self._size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.setPixmap(pixmap)
        self.setFixedSize(self._size, self._size)


class AppWelcomeWidget(QWidget):
    """
    Show icon and title.
    """

    _spacing: int = 8

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        header_layout = QGridLayout()
        header_layout.setSpacing(self._spacing)  # space between widgets
        header_layout.setContentsMargins(0, 0, 0, 0)  # space around the layout

        app_name_label = QLabel(APP_NAME)
        app_name_font = app_name_label.font()
        app_name_font.setPointSize(18)
        app_name_font.setBold(True)
        app_name_label.setFont(app_name_font)

        header_layout.addWidget(AppIconLabel(), 1, 1, 3, 1, alignment=Qt.AlignmentFlag.AlignTop)
        header_layout.addWidget(app_name_label, 1, 2)
        header_layout.addWidget(QLabel("OCR snipping tool for reading manga in Japanese."), 2, 2)
        header_layout.addWidget(QLabel("License: GNU AGPL v3 or later."), 3, 2)
        self.setLayout(header_layout)


FREE_SW_URL = "https://www.gnu.org/philosophy/free-sw.html"
ABOUT_TEXT = f"""
<h2>Become a contributor!</h2>
Lancet is {_linked(FREE_SW_URL, "libre software")} maintained by
{_linked(GITHUB_URL, 'Ajatt-Tools')} and its community.
We highly welcome new contributors!
Visit {_linked(GITHUB_URL, 'the GitHub')} to get started.
If you have any questions, {_linked(CHAT_URL, 'join our community')}.
"""


class AboutDialog(QDialog):
    """Dialog that shows information about the Lancet application."""

    _content_margins = (24, 16, 24, 16)
    _spacing: int = 8

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"About {APP_NAME}")
        self.setWindowIcon(QIcon(str(APP_LOGO_PATH)))
        self.setMinimumWidth(440)
        self._setup_ui()

    def _setup_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setSpacing(self._spacing)
        root_layout.setContentsMargins(*self._content_margins)

        # Icon
        root_layout.addWidget(AppWelcomeWidget())

        # Contribute
        contribute_label = QLabel(ABOUT_TEXT)
        contribute_label.setOpenExternalLinks(True)
        contribute_label.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse)
        contribute_label.setWordWrap(True)
        root_layout.addWidget(contribute_label)

        # Close button
        self._button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self._button_box.button(QDialogButtonBox.StandardButton.Cancel).setText("Close")
        self._button_box.button(QDialogButtonBox.StandardButton.Cancel).setDefault(True)
        qconnect(self._button_box.rejected, self.accept)
        root_layout.addWidget(self._button_box)


def playground() -> None:
    """Launch the About dialog standalone for testing."""
    app = QApplication(sys.argv)
    form = AboutDialog()
    form.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    playground()
