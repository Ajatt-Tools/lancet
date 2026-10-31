# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import os
import sys

import pytest
from beartype import beartype
from PyQt6.QtWidgets import QApplication


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """
    Runtime-check the arguments and return values of collected test functions.
    https://github.com/beartype/beartype
    """
    for item in items:
        if isinstance(item, pytest.Function):
            item.obj = beartype(item.obj)


@pytest.fixture(autouse=True)
def no_qt_callback_errors() -> Iterator[None]:
    """Fail with full tracebacks for Qt callback exceptions during a test and function-scoped cleanup.

    Session cleanup and callbacks not dispatched before fixture teardown are outside this guard's scope.
    """
    errors: list[str] = []
    # Keep our hook independent of test monkeypatch teardown and avoid retaining traceback frames.
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(
            sys,
            "excepthook",
            lambda kind, error, tb: errors.append("".join(traceback.format_exception(kind, error, tb))),
        )
        yield
        if errors:
            pytest.fail("Unhandled Qt callback exceptions:\n" + "\n".join(errors), pytrace=False)


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
    match instance := QApplication.instance():
        case None:
            return QApplication(["pytest"])
        case QApplication():
            return instance
        case _:
            raise RuntimeError("A QCoreApplication already exists; widget tests require QApplication")
