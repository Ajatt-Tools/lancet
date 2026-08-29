# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import json
import pathlib
import typing

import pytest

from lancet.actions import LancetAction
from lancet.config import Config, OcrDestination
from lancet.exceptions import ConfigReadError


class ConfigFileScenario(typing.NamedTuple):
    """A test scenario for Config.read_from_file."""

    json_data: dict[str, object] | None  # None means file does not exist
    expected_copy_to: OcrDestination
    expected_force_cpu: bool
    expected_warning_count: int


READ_SCENARIOS: dict[str, ConfigFileScenario] = {
    "missing_file": ConfigFileScenario(
        json_data=None,
        expected_copy_to=OcrDestination.goldendict,
        expected_force_cpu=False,
        expected_warning_count=0,
    ),
    "empty_json": ConfigFileScenario(
        json_data={},
        expected_copy_to=OcrDestination.goldendict,
        expected_force_cpu=False,
        expected_warning_count=0,
    ),
    "goldendict": ConfigFileScenario(
        json_data={"copy_to": "goldendict"},
        expected_copy_to=OcrDestination.goldendict,
        expected_force_cpu=False,
        expected_warning_count=0,
    ),
    "clipboard": ConfigFileScenario(
        json_data={"copy_to": "clipboard"},
        expected_copy_to=OcrDestination.clipboard,
        expected_force_cpu=False,
        expected_warning_count=0,
    ),
    "force_cpu_true": ConfigFileScenario(
        json_data={"force_cpu": True},
        expected_copy_to=OcrDestination.goldendict,
        expected_force_cpu=True,
        expected_warning_count=0,
    ),
    "invalid_copy_to_falls_back": ConfigFileScenario(
        json_data={"copy_to": "nonexistent_destination"},
        expected_copy_to=OcrDestination.goldendict,
        expected_force_cpu=False,
        expected_warning_count=1,
    ),
}


class TestConfigReadFromFile:
    """Test Config.read_from_file with various JSON file contents."""

    @pytest.mark.parametrize("scenario", READ_SCENARIOS.values(), ids=READ_SCENARIOS.keys())
    def test_copy_to(
        self, scenario: ConfigFileScenario, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
    ) -> None:
        """Test that copy_to and force_cpu are parsed correctly from config file."""
        warnings: list[str] = []
        cfg_path = tmp_path / "lancet.json"
        if scenario.json_data is not None:
            cfg_path.write_text(json.dumps(scenario.json_data), encoding="utf-8")
        monkeypatch.setattr("lancet.config.CFG_PATH", cfg_path)
        monkeypatch.setattr("lancet.config.logger.warning", lambda message: warnings.append(message))
        cfg = Config.read_from_file()
        assert cfg.copy_to == scenario.expected_copy_to
        assert cfg.force_cpu == scenario.expected_force_cpu
        assert len(warnings) == scenario.expected_warning_count


class TestConfigSaveToFile:
    """Test Config.save_to_file serialization."""

    @pytest.mark.parametrize(
        "copy_to, config_relpath, goldendict_path",
        [
            (OcrDestination.goldendict, "lancet.json", ""),
            (OcrDestination.clipboard, "subdir/lancet.json", "/opt/goldendict/goldendict"),
        ],
    )
    def test_round_trip(
        self,
        copy_to: OcrDestination,
        config_relpath: str,
        goldendict_path: str,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: pathlib.Path,
    ) -> None:
        """Test that saving and reading a config produces the same values."""
        cfg_path = tmp_path / config_relpath
        monkeypatch.setattr("lancet.config.CFG_PATH", cfg_path)
        cfg = Config(copy_to=copy_to, path_to_goldendict_executable=goldendict_path)
        cfg.save_to_file()
        assert cfg_path.is_file()
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
        assert data["copy_to"] == copy_to.name
        assert data["path_to_goldendict_executable"] == goldendict_path
        loaded = Config.read_from_file()
        assert loaded.copy_to == copy_to
        assert loaded.path_to_goldendict_executable == goldendict_path


class TestConfigReadInvalidFile:
    """Test Config.read_from_file with malformed files."""

    @pytest.mark.parametrize(
        "file_content",
        [
            "not json at all",
            "{invalid json",
            '{"unknown_field": "value"}',
        ],
    )
    def test_malformed_json_raises(
        self, file_content: str, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
    ) -> None:
        """Test that malformed JSON or unknown fields raise ConfigReadError."""
        cfg_path = tmp_path / "lancet.json"
        cfg_path.write_text(file_content, encoding="utf-8")
        monkeypatch.setattr("lancet.config.CFG_PATH", cfg_path)
        with pytest.raises(ConfigReadError):
            Config.read_from_file()


class GetPynputShortcutsScenario(typing.NamedTuple):
    """A scenario describing how Config's shortcut fields convert to pynput hotkeys."""

    ocr_shortcut: str
    ocr_page_shortcut: str
    screenshot_shortcut: str
    expected_hotkey_count: int
    expected_failure_count: int
    expected_actions: frozenset[LancetAction]


GET_PYNPUT_SHORTCUTS_SCENARIOS: dict[str, GetPynputShortcutsScenario] = {
    "all_defaults_two_hotkeys": GetPynputShortcutsScenario(
        ocr_shortcut="Alt+O",
        ocr_page_shortcut="Shift+Alt+O",
        screenshot_shortcut="",
        expected_hotkey_count=2,
        expected_failure_count=0,
        expected_actions=frozenset({LancetAction.ocr, LancetAction.detect_and_ocr}),
    ),
    "all_blank_yields_nothing": GetPynputShortcutsScenario(
        ocr_shortcut="",
        ocr_page_shortcut="",
        screenshot_shortcut="",
        expected_hotkey_count=0,
        expected_failure_count=0,
        expected_actions=frozenset(),
    ),
    "one_invalid_one_valid": GetPynputShortcutsScenario(
        ocr_shortcut="Alt+O",
        ocr_page_shortcut="GibberishKey+X",
        screenshot_shortcut="",
        expected_hotkey_count=1,
        expected_failure_count=1,
        expected_actions=frozenset({LancetAction.ocr}),
    ),
    "all_three_distinct_valid": GetPynputShortcutsScenario(
        ocr_shortcut="Alt+O",
        ocr_page_shortcut="Shift+Alt+O",
        screenshot_shortcut="Ctrl+Shift+S",
        expected_hotkey_count=3,
        expected_failure_count=0,
        expected_actions=frozenset(LancetAction),
    ),
}


class TestConfigGetPynputShortcuts:
    """Verify Config.get_pynput_shortcuts converts the three shortcut fields correctly."""

    @pytest.mark.parametrize(
        "scenario", GET_PYNPUT_SHORTCUTS_SCENARIOS.values(), ids=GET_PYNPUT_SHORTCUTS_SCENARIOS.keys()
    )
    def test_hotkey_count(self, scenario: GetPynputShortcutsScenario) -> None:
        """The number of resulting pynput hotkeys matches the scenario's expectation."""
        cfg = Config(
            ocr_shortcut=scenario.ocr_shortcut,
            ocr_page_shortcut=scenario.ocr_page_shortcut,
            screenshot_shortcut=scenario.screenshot_shortcut,
        )
        result = cfg.get_pynput_shortcuts()
        assert len(result.hotkeys) == scenario.expected_hotkey_count
        assert len(result.failures) == scenario.expected_failure_count
        assert frozenset(result.hotkeys.values()) == scenario.expected_actions
