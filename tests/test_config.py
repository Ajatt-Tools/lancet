# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import json
import typing

import pytest

from lancet.config import Config, OcrDestination
from lancet.exceptions import ConfigReadError


class ConfigFileScenario(typing.NamedTuple):
    """A test scenario for Config.read_from_file."""

    json_data: dict[str, object] | None  # None means file does not exist
    expected_copy_to: OcrDestination
    expected_force_cpu: bool


READ_SCENARIOS: dict[str, ConfigFileScenario] = {
    "missing_file": ConfigFileScenario(
        json_data=None,
        expected_copy_to=OcrDestination.goldendict,
        expected_force_cpu=False,
    ),
    "empty_json": ConfigFileScenario(
        json_data={},
        expected_copy_to=OcrDestination.goldendict,
        expected_force_cpu=False,
    ),
    "goldendict": ConfigFileScenario(
        json_data={"copy_to": "goldendict"},
        expected_copy_to=OcrDestination.goldendict,
        expected_force_cpu=False,
    ),
    "clipboard": ConfigFileScenario(
        json_data={"copy_to": "clipboard"},
        expected_copy_to=OcrDestination.clipboard,
        expected_force_cpu=False,
    ),
    "force_cpu_true": ConfigFileScenario(
        json_data={"force_cpu": True},
        expected_copy_to=OcrDestination.goldendict,
        expected_force_cpu=True,
    ),
    "invalid_copy_to_falls_back": ConfigFileScenario(
        json_data={"copy_to": "nonexistent_destination"},
        expected_copy_to=OcrDestination.goldendict,
        expected_force_cpu=False,
    ),
}


class TestConfigReadFromFile:
    """Test Config.read_from_file with various JSON file contents."""

    @pytest.mark.parametrize("scenario_name", READ_SCENARIOS.keys())
    def test_copy_to(
        self, scenario_name: str, monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory
    ) -> None:
        """Test that copy_to and force_cpu are parsed correctly from config file."""

        scenario = READ_SCENARIOS[scenario_name]
        cfg_path = tmp_path / "lancet.json"
        if scenario.json_data is not None:
            cfg_path.write_text(json.dumps(scenario.json_data), encoding="utf-8")
        monkeypatch.setattr("lancet.config.CFG_PATH", cfg_path)
        cfg = Config.read_from_file()
        assert cfg.copy_to == scenario.expected_copy_to
        assert cfg.force_cpu == scenario.expected_force_cpu


class TestConfigSaveToFile:
    """Test Config.save_to_file serialization."""

    @pytest.mark.parametrize(
        "copy_to, config_relpath",
        [
            (OcrDestination.goldendict, "lancet.json"),
            (OcrDestination.clipboard, "subdir/lancet.json"),
        ],
    )
    def test_round_trip(
        self,
        copy_to: OcrDestination,
        config_relpath: str,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: pytest.TempPathFactory,
    ) -> None:
        """Test that saving and reading a config produces the same values."""
        cfg_path = tmp_path / config_relpath
        monkeypatch.setattr("lancet.config.CFG_PATH", cfg_path)
        cfg = Config(copy_to=copy_to)
        cfg.save_to_file()
        assert cfg_path.is_file()
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
        assert data["copy_to"] == copy_to.name
        loaded = Config.read_from_file()
        assert loaded.copy_to == copy_to


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
        self, file_content: str, monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory
    ) -> None:
        """Test that malformed JSON or unknown fields raise ConfigReadError."""
        cfg_path = tmp_path / "lancet.json"
        cfg_path.write_text(file_content, encoding="utf-8")
        monkeypatch.setattr("lancet.config.CFG_PATH", cfg_path)
        with pytest.raises(ConfigReadError):
            Config.read_from_file()
