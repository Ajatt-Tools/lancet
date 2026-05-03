# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
import typing
from collections.abc import Sequence

import pytest
from pynput.keyboard import HotKey
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence

from lancet.config import Config
from lancet.exceptions import KeyboardShortcutParseError
from lancet.keyboard_shortcuts.listener import to_pynput_hotkey, to_pynput_shortcuts
from lancet.keyboard_shortcuts.types import (
    LancetShortcutEnum,
    PyShortcutStr,
    QtShortcutStr,
)
from tests.helpers import (
    QtShortcut,
    qt_shortcut_to_string,
)


class TestToPynputHotkeyValid:
    @pytest.mark.parametrize(
        "shortcut, expected",
        [
            # Basic modifier + letter (Qt output style)
            ("Ctrl+O", "<ctrl>+o"),
            ("Alt+S", "<alt>+s"),
            ("Shift+A", "<shift>+a"),
            # Multiple modifiers
            ("Alt+Shift+S", "<alt>+<shift>+s"),
            ("Ctrl+Shift+F", "<ctrl>+<shift>+f"),
            # Qt's "Meta" (Win/Super/Cmd) maps to pynput's "cmd"
            ("Meta+P", "<cmd>+p"),
            ("Meta+Alt+P", "<cmd>+<alt>+p"),
            # Alternative modifier spellings
            ("super+o", "<cmd>+o"),
            ("win+l", "<cmd>+l"),
            ("control+o", "<ctrl>+o"),
            ("cmd+o", "<cmd>+o"),
            # Function keys
            ("Ctrl+F5", "<ctrl>+<f5>"),
            ("Ctrl+Shift+F12", "<ctrl>+<shift>+<f12>"),
            ("Alt+F4", "<alt>+<f4>"),
            # Named trigger keys
            ("Alt+Tab", "<alt>+<tab>"),
            ("Ctrl+Shift+Space", "<ctrl>+<shift>+<space>"),
            ("Ctrl+Up", "<ctrl>+<up>"),
            ("Ctrl+Home", "<ctrl>+<home>"),
            ("Shift+Delete", "<shift>+<delete>"),
            # Whitespace around tokens is stripped
            (" Ctrl + O ", "<ctrl>+o"),
            ("  Meta  +  P  ", "<cmd>+p"),
        ],
    )
    def test_converts_correctly(self, shortcut: str, expected: str) -> None:
        assert to_pynput_hotkey(QtShortcutStr(shortcut)) == PyShortcutStr(expected)


# Real Qt modifier+key combinations the grab dialog could produce.
# Each is paired with the pynput format we expect to round-trip to.
VALID_QT_SHORTCUTS: Sequence[QtShortcut] = [
    # Single-letter triggers
    QtShortcut(Qt.KeyboardModifier.AltModifier, Qt.Key.Key_O, "<alt>+o"),
    QtShortcut(Qt.KeyboardModifier.ControlModifier, Qt.Key.Key_O, "<ctrl>+o"),
    QtShortcut(Qt.KeyboardModifier.ShiftModifier, Qt.Key.Key_A, "<shift>+a"),
    # Multiple modifiers
    QtShortcut(
        Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.ShiftModifier,
        Qt.Key.Key_O,
        "<alt>+<shift>+o",
    ),
    QtShortcut(
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
        Qt.Key.Key_F,
        "<ctrl>+<shift>+f",
    ),
    # Qt's MetaModifier (Win/Super/Cmd) → pynput's <cmd>
    QtShortcut(Qt.KeyboardModifier.MetaModifier, Qt.Key.Key_P, "<cmd>+p"),
    QtShortcut(
        Qt.KeyboardModifier.MetaModifier | Qt.KeyboardModifier.AltModifier,
        Qt.Key.Key_P,
        "<cmd>+<alt>+p",
    ),
    # Function keys
    QtShortcut(Qt.KeyboardModifier.ControlModifier, Qt.Key.Key_F5, "<ctrl>+<f5>"),
    QtShortcut(Qt.KeyboardModifier.AltModifier, Qt.Key.Key_F4, "<alt>+<f4>"),
    QtShortcut(
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
        Qt.Key.Key_F12,
        "<ctrl>+<shift>+<f12>",
    ),
    # Named trigger keys
    QtShortcut(Qt.KeyboardModifier.AltModifier, Qt.Key.Key_Tab, "<alt>+<tab>"),
    QtShortcut(
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
        Qt.Key.Key_Space,
        "<ctrl>+<shift>+<space>",
    ),
    QtShortcut(Qt.KeyboardModifier.ControlModifier, Qt.Key.Key_Up, "<ctrl>+<up>"),
    QtShortcut(Qt.KeyboardModifier.ControlModifier, Qt.Key.Key_Home, "<ctrl>+<home>"),
    # Qt abbreviates Delete to "Del"; our converter aliases it to pynput's canonical "delete".
    QtShortcut(Qt.KeyboardModifier.ShiftModifier, Qt.Key.Key_Delete, "<shift>+<delete>"),
]


class TestQtShortcutConversion:
    """Drive the converter with real QKeySequence-rendered strings, mirroring grab_key.py."""

    @pytest.mark.parametrize("qt_shortcut", VALID_QT_SHORTCUTS, ids=qt_shortcut_to_string)
    def test_qt_shortcut_converts_to_expected_pynput_form(self, qt_shortcut: QtShortcut) -> None:
        rendered = qt_shortcut_to_string(qt_shortcut)
        assert to_pynput_hotkey(QtShortcutStr(rendered)) == PyShortcutStr(qt_shortcut.expected_pynput)

    @pytest.mark.parametrize("qt_shortcut", VALID_QT_SHORTCUTS, ids=qt_shortcut_to_string)
    def test_qt_shortcut_accepted_by_pynput(self, qt_shortcut: QtShortcut) -> None:
        """The pynput form produced from a QKeySequence is accepted by pynput's HotKey.parse."""
        rendered = qt_shortcut_to_string(qt_shortcut)
        keys = HotKey.parse(to_pynput_hotkey(QtShortcutStr(rendered)))
        # Must yield at least one modifier and one trigger key.
        assert len(keys) >= 2


class TestToPynputHotkeyInvalid:
    @pytest.mark.parametrize(
        "shortcut",
        [
            # Empty / blank
            "",
            " ",
            "+",
            "  +  ",
            # Modifier only — no trigger key
            "Ctrl",
            "Ctrl+Shift",
            "Meta+Alt",
            # Unrecognised tokens
            "Conttrol+O",
            "Ctl+O",
            # Multi-character non-named trigger
            "Ctrl+abc",
            "Alt+F-key",
            # Trailing + produces no trigger after stripping
            "Ctrl+",
        ],
    )
    def test_raises_on_invalid(self, shortcut: str) -> None:
        with pytest.raises(KeyboardShortcutParseError):
            to_pynput_hotkey(QtShortcutStr(shortcut))


class TestInvalidQtShortcutSentinels:
    """Invalid shortcut strings can also be rejected when constructed via QKeySequence."""

    @pytest.mark.parametrize(
        "modifiers, key",
        [
            # Modifier-only QKeySequence: toString() emits e.g. "Ctrl+" which lacks a trigger.
            (Qt.KeyboardModifier.ControlModifier, Qt.Key.Key_unknown),
        ],
    )
    def test_modifier_only_raises(self, modifiers: Qt.KeyboardModifier, key: Qt.Key) -> None:
        rendered = QKeySequence(int(modifiers.value) + key).toString()
        with pytest.raises(KeyboardShortcutParseError):
            to_pynput_hotkey(QtShortcutStr(rendered))


def non_empty_default_shortcuts() -> Sequence[str]:
    """Return the non-empty default shortcuts from the Config dataclass."""
    return [s for s in (Config.ocr_shortcut, Config.ocr_page_shortcut, Config.screenshot_shortcut) if s]


class TestDefaultConfigShortcuts:
    """Ensure the default shortcuts shipped in Config are valid and pynput-compatible."""

    @pytest.mark.parametrize("shortcut", non_empty_default_shortcuts())
    def test_default_shortcut_converts(self, shortcut: str) -> None:
        """to_pynput_hotkey must not raise for default Config shortcuts."""
        assert to_pynput_hotkey(QtShortcutStr(shortcut))  # non-empty result

    @pytest.mark.parametrize("shortcut", non_empty_default_shortcuts())
    def test_default_shortcut_accepted_by_pynput(self, shortcut: str) -> None:
        """pynput's HotKey.parse must accept the converted default shortcuts."""
        keys = HotKey.parse(to_pynput_hotkey(QtShortcutStr(shortcut)))
        assert len(keys) >= 2  # at least one modifier + one trigger key


class ConversionScenario(typing.NamedTuple):
    """A test scenario for to_pynput_shortcuts batch conversion."""

    shortcuts: dict[QtShortcutStr, LancetShortcutEnum]
    expected_hotkey_count: int
    expected_failure_count: int


CONVERSION_SCENARIOS: dict[str, ConversionScenario] = {
    "two_valid": ConversionScenario(
        shortcuts={
            QtShortcutStr("Alt+O"): LancetShortcutEnum.ocr_shortcut,
            QtShortcutStr("Shift+Alt+O"): LancetShortcutEnum.ocr_page_shortcut,
        },
        expected_hotkey_count=2,
        expected_failure_count=0,
    ),
    "empty_skipped": ConversionScenario(
        shortcuts={
            QtShortcutStr(""): LancetShortcutEnum.screenshot_shortcut,
            QtShortcutStr("Alt+O"): LancetShortcutEnum.ocr_shortcut,
        },
        expected_hotkey_count=1,
        expected_failure_count=0,
    ),
    "whitespace_skipped": ConversionScenario(
        shortcuts={
            QtShortcutStr("   "): LancetShortcutEnum.screenshot_shortcut,
        },
        expected_hotkey_count=0,
        expected_failure_count=0,
    ),
    "invalid_collected": ConversionScenario(
        shortcuts={
            QtShortcutStr("Alt+O"): LancetShortcutEnum.ocr_shortcut,
            QtShortcutStr("InvalidKey+X"): LancetShortcutEnum.ocr_page_shortcut,
        },
        expected_hotkey_count=1,
        expected_failure_count=1,
    ),
    "modifier_only_collected": ConversionScenario(
        shortcuts={
            QtShortcutStr("Ctrl+Shift"): LancetShortcutEnum.ocr_shortcut,
        },
        expected_hotkey_count=0,
        expected_failure_count=1,
    ),
    "all_empty": ConversionScenario(
        shortcuts={
            QtShortcutStr(""): LancetShortcutEnum.ocr_shortcut,
            QtShortcutStr(""): LancetShortcutEnum.ocr_page_shortcut,
        },
        expected_hotkey_count=0,
        expected_failure_count=0,
    ),
}


class TestToPynputShortcuts:
    """Test batch conversion of shortcuts to pynput format."""

    @pytest.mark.parametrize("scenario_name", CONVERSION_SCENARIOS.keys())
    def test_hotkey_count(self, scenario_name: str) -> None:
        """Test that the correct number of hotkeys are converted."""
        scenario = CONVERSION_SCENARIOS[scenario_name]
        result = to_pynput_shortcuts(scenario.shortcuts)
        assert len(result.hotkeys) == scenario.expected_hotkey_count
        assert len(result.failures) == scenario.expected_failure_count
