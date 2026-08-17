# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import os

import pytest
from PyQt6.QtWidgets import QApplication


@pytest.fixture(scope="session", autouse=True)
def qt_offscreen_platform() -> None:
    """Force Qt to run without a real display so widget tests work in headless CI."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session", autouse=True)
def qapp(qt_offscreen_platform: None) -> QApplication:
    """Ensure a QApplication exists for widget tests.

    A program name must be present in argv because Qt aborts
    when QApplication is created with an empty argument list.
    """
    return QApplication.instance() or QApplication(["pytest"])
