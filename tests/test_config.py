# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import json
import os
import pathlib
import stat
import typing

import pytest

from lancet.actions import LancetAction
from lancet.anki.image_types import AnkiImageFormat, ImageParameters
from lancet.config import Config, OcrDestination
from lancet.consts import (
    ANKI_FIELD_SEPARATOR,
    ANKI_IMAGE_MAX_DIMENSION,
    ANKI_IMAGE_MAX_QUALITY,
    CONFIG_FILE_MODE,
    IS_WIN,
)
from lancet.exceptions import ConfigReadError


class ConfigDumpRecorder:
    """Observe a temporary configuration file while replacing JSON serialization."""

    def __init__(self) -> None:
        """Initialize the empty temporary-file observation lists."""
        self.paths: list[pathlib.Path] = []
        self.modes: list[int] = []

    def __call__(
        self,
        _data: object,
        output: typing.TextIO,
        *,
        ensure_ascii: bool,
        indent: int,
    ) -> None:
        """Record file metadata and write a minimal valid JSON object."""
        self.paths.append(pathlib.Path(output.name))
        self.modes.append(stat.S_IMODE(os.fstat(output.fileno()).st_mode))
        output.write("{}")


class ReplaceFailure:
    """Raise one caller-owned error when atomic config replacement is attempted."""

    def __init__(self, error: OSError) -> None:
        """Store the exact replacement failure expected by the test."""
        self._error = error

    def __call__(self, *_paths: pathlib.Path) -> pathlib.Path:
        """Raise the stored replacement error without altering either path."""
        raise self._error


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


class AnkiFormatScenario(typing.NamedTuple):
    """A serialized Anki image format and the enum expected after config parsing."""

    serialized: object
    expected: AnkiImageFormat
    expected_warning_count: int


ANKI_FORMAT_SCENARIOS: dict[str, AnkiFormatScenario] = {
    "avif": AnkiFormatScenario("avif", AnkiImageFormat.avif, 0),
    "webp": AnkiFormatScenario("webp", AnkiImageFormat.webp, 0),
    "invalid_name_uses_default": AnkiFormatScenario("png", AnkiImageFormat.avif, 1),
    "invalid_type_uses_default": AnkiFormatScenario(None, AnkiImageFormat.avif, 1),
}


class TestConfigAnkiImageFormat:
    """Test Anki image-format enum parsing and fallback behavior."""

    @pytest.mark.parametrize("scenario", ANKI_FORMAT_SCENARIOS.values(), ids=ANKI_FORMAT_SCENARIOS.keys())
    def test_read(self, scenario: AnkiFormatScenario, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
        """Serialized format names become enum members, while invalid names use the AVIF default."""
        warnings: list[str] = []
        cfg_path = tmp_path / "lancet.json"
        cfg_path.write_text(json.dumps({"anki_image_format": scenario.serialized}), encoding="utf-8")
        monkeypatch.setattr("lancet.config.CFG_PATH", cfg_path)
        monkeypatch.setattr("lancet.config.logger.warning", lambda message: warnings.append(message))
        assert Config.read_from_file().anki_image_format == scenario.expected
        assert len(warnings) == scenario.expected_warning_count


class ImageSettingsScenario(typing.NamedTuple):
    """Serialized image settings and their normalized configuration values."""

    source: ImageParameters
    expected: ImageParameters


IMAGE_SETTINGS_SCENARIOS: dict[str, ImageSettingsScenario] = {
    "negative_values": ImageSettingsScenario(
        source=ImageParameters(width=-1, height=-100, quality=-1),
        expected=ImageParameters(width=0, height=0, quality=0),
    ),
    "in_range_values": ImageSettingsScenario(
        source=ImageParameters(width=600, height=250, quality=33),
        expected=ImageParameters(width=600, height=250, quality=33),
    ),
    "values_above_limit": ImageSettingsScenario(
        source=ImageParameters(
            width=ANKI_IMAGE_MAX_DIMENSION + 1,
            height=ANKI_IMAGE_MAX_DIMENSION + 100,
            quality=ANKI_IMAGE_MAX_QUALITY + 1,
        ),
        expected=ImageParameters(
            width=ANKI_IMAGE_MAX_DIMENSION,
            height=ANKI_IMAGE_MAX_DIMENSION,
            quality=ANKI_IMAGE_MAX_QUALITY,
        ),
    ),
}


class TestConfigAnkiImageSettings:
    """Test Anki image dimension and quality normalization at configuration boundaries."""

    @pytest.mark.parametrize("scenario", IMAGE_SETTINGS_SCENARIOS.values(), ids=IMAGE_SETTINGS_SCENARIOS.keys())
    def test_read_clamps_dimensions(
        self, scenario: ImageSettingsScenario, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
    ) -> None:
        """Config reads clamp image dimensions and quality to the UI-supported range."""
        cfg_path = tmp_path / "lancet.json"
        cfg_path.write_text(
            json.dumps(
                {
                    "anki_image_width": scenario.source.width,
                    "anki_image_height": scenario.source.height,
                    "anki_image_quality": scenario.source.quality,
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr("lancet.config.CFG_PATH", cfg_path)

        cfg = Config.read_from_file()

        assert cfg.anki_image_width == scenario.expected.width
        assert cfg.anki_image_height == scenario.expected.height
        assert cfg.anki_image_quality == scenario.expected.quality

    @pytest.mark.parametrize("scenario", IMAGE_SETTINGS_SCENARIOS.values(), ids=IMAGE_SETTINGS_SCENARIOS.keys())
    def test_save_clamps_dimensions(
        self, scenario: ImageSettingsScenario, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
    ) -> None:
        """Config saves normalized constructor settings to both memory and JSON."""
        cfg_path = tmp_path / "lancet.json"
        monkeypatch.setattr("lancet.config.CFG_PATH", cfg_path)
        cfg = Config(
            anki_image_width=scenario.source.width,
            anki_image_height=scenario.source.height,
            anki_image_quality=scenario.source.quality,
        )

        cfg.save_to_file()

        assert cfg.anki_image_width == scenario.expected.width
        assert cfg.anki_image_height == scenario.expected.height
        assert cfg.anki_image_quality == scenario.expected.quality
        saved = json.loads(cfg_path.read_text(encoding="utf-8"))
        assert saved["anki_image_width"] == scenario.expected.width
        assert saved["anki_image_height"] == scenario.expected.height
        assert saved["anki_image_quality"] == scenario.expected.quality


class AnkiTextScenario(typing.NamedTuple):
    """One persisted Anki text field and the value retained at both config boundaries."""

    key: str
    serialized: str
    expected: str


ANKI_TEXT_SCENARIOS: dict[str, AnkiTextScenario] = {
    "connect_url_strips": AnkiTextScenario(
        key="anki_connect_url",
        serialized="  http://127.0.0.1:8765  ",
        expected="http://127.0.0.1:8765",
    ),
    "image_field_strips": AnkiTextScenario(
        key="anki_image_field",
        serialized="  Image  ",
        expected="Image",
    ),
    "api_key_preserves": AnkiTextScenario(
        key="anki_connect_api_key",
        serialized="  key  ",
        expected="  key  ",
    ),
    "separator_preserves": AnkiTextScenario(
        key="anki_field_separator",
        serialized="  <hr>  ",
        expected="  <hr>  ",
    ),
}


class TestConfigAnkiTextSettings:
    """Test Anki text normalization at persisted configuration boundaries."""

    @pytest.mark.parametrize("scenario", ANKI_TEXT_SCENARIOS.values(), ids=ANKI_TEXT_SCENARIOS.keys())
    def test_read_and_save(
        self,
        scenario: AnkiTextScenario,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: pathlib.Path,
    ) -> None:
        """URL and field trim while API keys and HTML separators preserve significant whitespace."""
        cfg_path = tmp_path / "lancet.json"
        cfg_path.write_text(json.dumps({scenario.key: scenario.serialized}), encoding="utf-8")
        monkeypatch.setattr("lancet.config.CFG_PATH", cfg_path)
        cfg = Config.read_from_file()
        assert getattr(cfg, scenario.key) == scenario.expected
        cfg.save_to_file()
        assert json.loads(cfg_path.read_text(encoding="utf-8"))[scenario.key] == scenario.expected


class AnkiDefaultsScenario(typing.NamedTuple):
    """The Anki defaults that must produce an enabled screenshot shortcut."""

    shortcut: str
    field_separator: str
    image_format: AnkiImageFormat
    expected_actions: frozenset[LancetAction]


ANKI_DEFAULT_SCENARIOS: dict[str, AnkiDefaultsScenario] = {
    "default_config": AnkiDefaultsScenario(
        shortcut="Alt+I",
        field_separator=ANKI_FIELD_SEPARATOR,
        image_format=AnkiImageFormat.avif,
        expected_actions=frozenset({LancetAction.ocr, LancetAction.detect_and_ocr, LancetAction.screenshot_to_anki}),
    ),
}


class TestConfigAnkiDefaults:
    """Test that a fresh configuration enables the documented Anki defaults."""

    @pytest.mark.parametrize("scenario", ANKI_DEFAULT_SCENARIOS.values(), ids=ANKI_DEFAULT_SCENARIOS.keys())
    def test_defaults(self, scenario: AnkiDefaultsScenario) -> None:
        """Fresh configuration values produce the expected Anki shortcut action."""
        config = Config()
        assert config.anki_shortcut == scenario.shortcut
        assert config.anki_field_separator == scenario.field_separator
        assert config.anki_image_format == scenario.image_format
        assert frozenset(config.get_pynput_shortcuts().hotkeys.values()) == scenario.expected_actions


class ConfigRoundTripScenario(typing.NamedTuple):
    """Non-default configuration values that must survive JSON serialization."""

    copy_to: OcrDestination
    config_relpath: str
    goldendict_path: str
    image_format: AnkiImageFormat
    field_separator: str


ROUND_TRIP_SCENARIOS: dict[str, ConfigRoundTripScenario] = {
    "default_avif": ConfigRoundTripScenario(
        copy_to=OcrDestination.goldendict,
        config_relpath="lancet.json",
        goldendict_path="",
        image_format=AnkiImageFormat.avif,
        field_separator=ANKI_FIELD_SEPARATOR,
    ),
    "custom_webp_separator": ConfigRoundTripScenario(
        copy_to=OcrDestination.clipboard,
        config_relpath="subdir/lancet.json",
        goldendict_path="/opt/goldendict/goldendict",
        image_format=AnkiImageFormat.webp,
        field_separator="<hr>",
    ),
}


class TestConfigSaveToFile:
    """Test Config.save_to_file serialization."""

    @pytest.mark.parametrize("scenario", ROUND_TRIP_SCENARIOS.values(), ids=ROUND_TRIP_SCENARIOS.keys())
    def test_round_trip(
        self,
        scenario: ConfigRoundTripScenario,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: pathlib.Path,
    ) -> None:
        """Test that saving and reading a config produces the same values."""
        cfg_path = tmp_path / scenario.config_relpath
        monkeypatch.setattr("lancet.config.CFG_PATH", cfg_path)
        cfg = Config(
            copy_to=scenario.copy_to,
            path_to_goldendict_executable=scenario.goldendict_path,
            anki_image_format=scenario.image_format,
            anki_field_separator=scenario.field_separator,
        )
        cfg.save_to_file()
        assert cfg_path.is_file()
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
        assert data["copy_to"] == scenario.copy_to.name
        assert data["anki_image_format"] == scenario.image_format.name
        assert data["anki_field_separator"] == scenario.field_separator
        assert data["path_to_goldendict_executable"] == scenario.goldendict_path
        loaded = Config.read_from_file()
        assert loaded.copy_to == scenario.copy_to
        assert loaded.anki_image_format == scenario.image_format
        assert loaded.anki_field_separator == scenario.field_separator
        assert loaded.path_to_goldendict_executable == scenario.goldendict_path

    CONFIG_PERMISSION_SCENARIOS: dict[str, str] = {"existing_permissive_file": "secret"}

    @pytest.mark.parametrize(
        "api_key",
        CONFIG_PERMISSION_SCENARIOS.values(),
        ids=CONFIG_PERMISSION_SCENARIOS.keys(),
    )
    @pytest.mark.skipif(IS_WIN, reason="Windows chmod does not enforce POSIX owner-only permissions")
    def test_restricts_file_permissions(
        self,
        api_key: str,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: pathlib.Path,
    ) -> None:
        """Saving a plaintext Anki API key restricts the configuration file mode."""
        cfg_path = tmp_path / "lancet.json"
        cfg_path.touch(mode=0o644)
        monkeypatch.setattr("lancet.config.CFG_PATH", cfg_path)
        Config(anki_connect_api_key=api_key).save_to_file()
        assert stat.S_IMODE(cfg_path.stat().st_mode) == CONFIG_FILE_MODE

    @pytest.mark.skipif(IS_WIN, reason="Windows chmod does not enforce POSIX owner-only permissions")
    def test_new_file_is_restricted_during_write(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: pathlib.Path,
    ) -> None:
        """A new config temporary file is owner-only before writing the API key."""
        cfg_path = tmp_path / "lancet.json"
        recorder = ConfigDumpRecorder()
        monkeypatch.setattr("lancet.config.CFG_PATH", cfg_path)
        monkeypatch.setattr("lancet.config.json.dump", recorder)
        Config(anki_connect_api_key="secret").save_to_file()

        assert len(recorder.paths) == 1
        assert recorder.paths[0].parent == cfg_path.parent
        assert recorder.paths[0] != cfg_path
        assert recorder.modes == [CONFIG_FILE_MODE]
        assert cfg_path.read_text(encoding="utf-8") == "{}"
        assert recorder.paths[0].exists() is False

    def test_failed_save_does_not_chmod_directory(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: pathlib.Path,
    ) -> None:
        """A directory at the config path keeps its mode when replacement fails."""
        cfg_path = tmp_path / "lancet.json"
        cfg_path.mkdir()
        cfg_path.chmod(0o755)
        mode_before = stat.S_IMODE(cfg_path.stat().st_mode)
        monkeypatch.setattr("lancet.config.CFG_PATH", cfg_path)

        with pytest.raises(OSError):
            Config().save_to_file()

        assert stat.S_IMODE(cfg_path.stat().st_mode) == mode_before

    def test_failed_serialization_preserves_existing_config(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: pathlib.Path,
    ) -> None:
        """A failed temporary write leaves the previous config file untouched."""
        cfg_path = tmp_path / "lancet.json"
        original_content = '{"old": true}'
        cfg_path.write_text(original_content, encoding="utf-8")
        monkeypatch.setattr("lancet.config.CFG_PATH", cfg_path)
        monkeypatch.setattr(
            "lancet.config.json.dump", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("write failed"))
        )

        with pytest.raises(OSError, match="write failed"):
            Config().save_to_file()

        assert cfg_path.read_text(encoding="utf-8") == original_content

    def test_failed_replacement_preserves_existing_config(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: pathlib.Path,
    ) -> None:
        """A failed atomic replacement preserves the old config and cleans its temporary sibling."""
        cfg_path = tmp_path / "lancet.json"
        original_content = '{"old": true}'
        replace_error = OSError("replace failed")
        cfg_path.write_text(original_content, encoding="utf-8")
        monkeypatch.setattr("lancet.config.CFG_PATH", cfg_path)
        monkeypatch.setattr(pathlib.Path, "replace", ReplaceFailure(replace_error))

        with pytest.raises(OSError) as exc_info:
            Config().save_to_file()

        assert exc_info.value is replace_error
        assert cfg_path.read_text(encoding="utf-8") == original_content
        assert list(tmp_path.glob(".lancet.json.*.tmp")) == []
        assert list(tmp_path.glob(".lancet.json.*.tmp")) == []

    @pytest.mark.skipif(IS_WIN, reason="Windows symlink behavior differs from POSIX replacement semantics")
    def test_replaces_config_symlink_without_modifying_target(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: pathlib.Path,
    ) -> None:
        """Atomic replacement replaces a config symlink instead of following its target."""
        cfg_path = tmp_path / "lancet.json"
        target_path = tmp_path / "target.json"
        target_content = '{"target": true}'
        target_path.write_text(target_content, encoding="utf-8")
        cfg_path.symlink_to(target_path)
        monkeypatch.setattr("lancet.config.CFG_PATH", cfg_path)

        Config().save_to_file()

        assert cfg_path.is_symlink() is False
        assert target_path.read_text(encoding="utf-8") == target_content


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
    anki_shortcut: str
    expected_hotkey_count: int
    expected_failure_count: int
    expected_actions: frozenset[LancetAction]


GET_PYNPUT_SHORTCUTS_SCENARIOS: dict[str, GetPynputShortcutsScenario] = {
    "all_defaults_three_hotkeys": GetPynputShortcutsScenario(
        ocr_shortcut="Alt+O",
        ocr_page_shortcut="Shift+Alt+O",
        screenshot_shortcut="",
        anki_shortcut="Alt+I",
        expected_hotkey_count=3,
        expected_failure_count=0,
        expected_actions=frozenset({LancetAction.ocr, LancetAction.detect_and_ocr, LancetAction.screenshot_to_anki}),
    ),
    "all_blank_yields_nothing": GetPynputShortcutsScenario(
        ocr_shortcut="",
        ocr_page_shortcut="",
        screenshot_shortcut="",
        anki_shortcut="",
        expected_hotkey_count=0,
        expected_failure_count=0,
        expected_actions=frozenset(),
    ),
    "one_invalid_two_valid": GetPynputShortcutsScenario(
        ocr_shortcut="Alt+O",
        ocr_page_shortcut="GibberishKey+X",
        screenshot_shortcut="",
        anki_shortcut="Alt+I",
        expected_hotkey_count=2,
        expected_failure_count=1,
        expected_actions=frozenset({LancetAction.ocr, LancetAction.screenshot_to_anki}),
    ),
    "all_four_distinct_valid": GetPynputShortcutsScenario(
        ocr_shortcut="Alt+O",
        ocr_page_shortcut="Shift+Alt+O",
        screenshot_shortcut="Ctrl+Shift+S",
        anki_shortcut="Alt+I",
        expected_hotkey_count=4,
        expected_failure_count=0,
        expected_actions=frozenset(LancetAction),
    ),
}


class TestConfigGetPynputShortcuts:
    """Verify Config.get_pynput_shortcuts converts all four shortcut fields correctly."""

    @pytest.mark.parametrize(
        "scenario", GET_PYNPUT_SHORTCUTS_SCENARIOS.values(), ids=GET_PYNPUT_SHORTCUTS_SCENARIOS.keys()
    )
    def test_hotkey_count(self, scenario: GetPynputShortcutsScenario) -> None:
        """The number of resulting pynput hotkeys matches the scenario's expectation."""
        cfg = Config(
            ocr_shortcut=scenario.ocr_shortcut,
            ocr_page_shortcut=scenario.ocr_page_shortcut,
            screenshot_shortcut=scenario.screenshot_shortcut,
            anki_shortcut=scenario.anki_shortcut,
        )
        result = cfg.get_pynput_shortcuts()
        assert len(result.hotkeys) == scenario.expected_hotkey_count
        assert len(result.failures) == scenario.expected_failure_count
        assert frozenset(result.hotkeys.values()) == scenario.expected_actions
