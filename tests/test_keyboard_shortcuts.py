# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
import typing
from collections.abc import Sequence

import pytest
from pynput.keyboard import HotKey
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence

from lancet.actions import LancetAction
from lancet.config import Config
from lancet.exceptions import KeyboardShortcutParseError
from lancet.keyboard_shortcuts.listener import to_pynput_hotkey, to_pynput_shortcuts
from lancet.keyboard_shortcuts.types import (
    PyShortcutStr,
    QtShortcutStr,
)
from tests.helpers import (
    QtShortcut,
    qt_shortcut_to_string,
)


class ShortcutConversionScenario(typing.NamedTuple):
    """A Qt shortcut string and the expected pynput representation."""

    shortcut: str
    expected: str


SHORTCUT_CONVERSION_SCENARIOS: dict[str, ShortcutConversionScenario] = {
    # Basic modifier + letter (Qt output style)
    "ctrl_letter": ShortcutConversionScenario("Ctrl+O", "<ctrl>+o"),
    "alt_letter": ShortcutConversionScenario("Alt+S", "<alt>+s"),
    "shift_letter": ShortcutConversionScenario("Shift+A", "<shift>+a"),
    # Multiple modifiers
    "alt_shift": ShortcutConversionScenario("Alt+Shift+S", "<alt>+<shift>+s"),
    "ctrl_shift": ShortcutConversionScenario("Ctrl+Shift+F", "<ctrl>+<shift>+f"),
    # Qt's "Meta" (Win/Super/Cmd) maps to pynput's "cmd"
    "meta": ShortcutConversionScenario("Meta+P", "<cmd>+p"),
    "meta_alt": ShortcutConversionScenario("Meta+Alt+P", "<cmd>+<alt>+p"),
    # Alternative modifier spellings
    "super_alias": ShortcutConversionScenario("super+o", "<cmd>+o"),
    "win_alias": ShortcutConversionScenario("win+l", "<cmd>+l"),
    "control_alias": ShortcutConversionScenario("control+o", "<ctrl>+o"),
    "cmd_alias": ShortcutConversionScenario("cmd+o", "<cmd>+o"),
    # Function keys
    "function_key": ShortcutConversionScenario("Ctrl+F5", "<ctrl>+<f5>"),
    "shift_function_key": ShortcutConversionScenario("Ctrl+Shift+F12", "<ctrl>+<shift>+<f12>"),
    "alt_function_key": ShortcutConversionScenario("Alt+F4", "<alt>+<f4>"),
    # Named trigger keys
    "tab": ShortcutConversionScenario("Alt+Tab", "<alt>+<tab>"),
    "space": ShortcutConversionScenario("Ctrl+Shift+Space", "<ctrl>+<shift>+<space>"),
    "up": ShortcutConversionScenario("Ctrl+Up", "<ctrl>+<up>"),
    "home": ShortcutConversionScenario("Ctrl+Home", "<ctrl>+<home>"),
    "delete": ShortcutConversionScenario("Shift+Delete", "<shift>+<delete>"),
    # Whitespace around tokens is stripped
    "trim_ctrl": ShortcutConversionScenario(" Ctrl + O ", "<ctrl>+o"),
    "trim_meta": ShortcutConversionScenario("  Meta  +  P  ", "<cmd>+p"),
}


class TestToPynputHotkeyValid:
    @pytest.mark.parametrize(
        "scenario", SHORTCUT_CONVERSION_SCENARIOS.values(), ids=SHORTCUT_CONVERSION_SCENARIOS.keys()
    )
    def test_converts_correctly(self, scenario: ShortcutConversionScenario) -> None:
        """Convert each Qt shortcut to its expected pynput representation."""
        assert to_pynput_hotkey(QtShortcutStr(scenario.shortcut)) == PyShortcutStr(scenario.expected)


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

    def test_modifier_only_raises(self) -> None:
        """Reject a modifier-only key sequence without a trigger key."""
        # Modifier-only QKeySequence: toString() emits e.g. "Ctrl+" which lacks a trigger.
        rendered = QKeySequence(int(Qt.KeyboardModifier.ControlModifier.value) + Qt.Key.Key_unknown).toString()
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

    shortcuts: dict[QtShortcutStr, LancetAction]
    expected_hotkey_count: int
    expected_failure_count: int


CONVERSION_SCENARIOS: dict[str, ConversionScenario] = {
    "two_valid": ConversionScenario(
        shortcuts={
            QtShortcutStr("Alt+O"): LancetAction.ocr,
            QtShortcutStr("Shift+Alt+O"): LancetAction.detect_and_ocr,
        },
        expected_hotkey_count=2,
        expected_failure_count=0,
    ),
    "empty_skipped": ConversionScenario(
        shortcuts={
            QtShortcutStr(""): LancetAction.screenshot,
            QtShortcutStr("Alt+O"): LancetAction.ocr,
        },
        expected_hotkey_count=1,
        expected_failure_count=0,
    ),
    "whitespace_skipped": ConversionScenario(
        shortcuts={
            QtShortcutStr("   "): LancetAction.screenshot,
        },
        expected_hotkey_count=0,
        expected_failure_count=0,
    ),
    "invalid_collected": ConversionScenario(
        shortcuts={
            QtShortcutStr("Alt+O"): LancetAction.ocr,
            QtShortcutStr("InvalidKey+X"): LancetAction.detect_and_ocr,
        },
        expected_hotkey_count=1,
        expected_failure_count=1,
    ),
    "modifier_only_collected": ConversionScenario(
        shortcuts={
            QtShortcutStr("Ctrl+Shift"): LancetAction.ocr,
        },
        expected_hotkey_count=0,
        expected_failure_count=1,
    ),
    "all_empty": ConversionScenario(
        shortcuts={
            QtShortcutStr(""): LancetAction.ocr,
            QtShortcutStr(" "): LancetAction.detect_and_ocr,
        },
        expected_hotkey_count=0,
        expected_failure_count=0,
    ),
}


class TestToPynputShortcuts:
    """Test batch conversion of shortcuts to pynput format."""

    @pytest.mark.parametrize("scenario", CONVERSION_SCENARIOS.values(), ids=CONVERSION_SCENARIOS.keys())
    def test_hotkey_count(self, scenario: ConversionScenario) -> None:
        """Test that the correct number of hotkeys are converted."""
        result = to_pynput_shortcuts(scenario.shortcuts)
        assert len(result.hotkeys) == scenario.expected_hotkey_count
        assert len(result.failures) == scenario.expected_failure_count
