# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""
Tests for read_config_file recovery behavior.
"""

import builtins
import functools
import importlib.metadata
import json
import pathlib
import typing
from collections.abc import Callable, Sequence
from unittest.mock import Mock, create_autospec

import pytest

from lancet.cli import CLI, log_dependency_versions
from lancet.config import Config, ConfigFileReadResult, OcrDestination, read_config_file
from lancet.exceptions import ConfigReadError
from lancet.ipc.client import LancetIpcClient
from lancet.ipc.types import IpcResponse, IpcStatus

OpenFn = Callable[..., typing.IO[str]]


def permission_denied_open(
    real_open: OpenFn,
    blocked_path: pathlib.Path,
    file: pathlib.Path | str,
    *args: object,
    **kwargs: object,
) -> typing.IO[str]:
    """Raise PermissionError for blocked_path and delegate every other call to real_open."""
    if str(file) == str(blocked_path):
        raise PermissionError(13, "Permission denied", str(blocked_path))
    return real_open(file, *args, **kwargs)


class ReadRecoveryScenario(typing.NamedTuple):
    """A scenario for read_config_file recovery from a malformed/unreadable config."""

    file_content: str | None  # None means "do not create the file"
    expect_error_substring: str  # Empty means no error expected.


RECOVERY_SCENARIOS: dict[str, ReadRecoveryScenario] = {
    "happy_path_returns_config": ReadRecoveryScenario(
        file_content=json.dumps({"copy_to": "clipboard"}),
        expect_error_substring="",
    ),
    "missing_file_returns_defaults": ReadRecoveryScenario(
        file_content=None,
        expect_error_substring="",
    ),
    "malformed_json_returns_defaults_with_error": ReadRecoveryScenario(
        file_content="{not valid json",
        expect_error_substring="failed to decode json config file",
    ),
    "unknown_field_returns_defaults_with_error": ReadRecoveryScenario(
        file_content=json.dumps({"unknown_field": "value"}),
        expect_error_substring="failed to parse config file",
    ),
    "non_object_json_returns_defaults_with_error": ReadRecoveryScenario(
        file_content="[]",
        expect_error_substring="top-level JSON value must be an object",
    ),
    "unhashable_copy_to_uses_default": ReadRecoveryScenario(
        file_content=json.dumps({"copy_to": []}),
        expect_error_substring="",
    ),
    "wrong_goldendict_path_type_returns_defaults_with_error": ReadRecoveryScenario(
        file_content=json.dumps({"path_to_goldendict_executable": {}}),
        expect_error_substring="failed to parse config file",
    ),
}


def write_scenario_config(scenario: ReadRecoveryScenario, tmp_path: pathlib.Path) -> pathlib.Path:
    """Create a scenario's config file under tmp_path and return its path."""
    cfg_path = tmp_path / "lancet.json"
    if scenario.file_content is not None:
        cfg_path.write_text(scenario.file_content, encoding="utf-8")
    return cfg_path


class TestReadConfigFileRecovery:
    """Verify read_config_file's recovery contract for each malformed-file scenario."""

    @pytest.mark.parametrize("scenario", RECOVERY_SCENARIOS.values(), ids=RECOVERY_SCENARIOS.keys())
    def test_returns_config_file_read_result(
        self, scenario: ReadRecoveryScenario, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
    ) -> None:
        """For every scenario, read_config_file must return a ConfigFileReadResult, never raise."""
        cfg_path = write_scenario_config(scenario, tmp_path)
        monkeypatch.setattr("lancet.config.CFG_PATH", cfg_path)

        result = read_config_file()
        assert isinstance(result, ConfigFileReadResult)
        assert isinstance(result.cfg, Config)

    @pytest.mark.parametrize("scenario", RECOVERY_SCENARIOS.values(), ids=RECOVERY_SCENARIOS.keys())
    def test_error_substring_matches(
        self, scenario: ReadRecoveryScenario, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
    ) -> None:
        """The error string carried by ConfigFileReadResult matches the failure mode."""
        cfg_path = write_scenario_config(scenario, tmp_path)
        monkeypatch.setattr("lancet.config.CFG_PATH", cfg_path)

        result = read_config_file()
        if scenario.expect_error_substring:
            assert scenario.expect_error_substring in result.error
        else:
            assert result.error == ""


class TestReadConfigFileBackupOnError:
    """When the existing config is malformed, the file must be renamed aside."""

    def test_malformed_json_renames_to_old(self, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
        """A corrupt config is moved to .old to make room for a fresh default config."""
        cfg_path = tmp_path / "lancet.json"
        cfg_path.write_text("{not valid json", encoding="utf-8")
        monkeypatch.setattr("lancet.config.CFG_PATH", cfg_path)

        result = read_config_file()
        assert not cfg_path.is_file()
        assert (tmp_path / "lancet.old").is_file()
        # Defaults are returned regardless.
        assert result.cfg.copy_to == OcrDestination.goldendict


class OSErrorScenario(typing.NamedTuple):
    """A scenario for triggering OSError from Config.read_from_file via different mechanisms."""

    setup: Callable[[pathlib.Path], pathlib.Path]
    """Receives tmp_path, returns the cfg_path that should be set as CFG_PATH."""

    patch_open: bool
    """If True, monkeypatch builtins.open to raise PermissionError for cfg_path."""


def setup_directory_at_cfg_path(tmp_path: pathlib.Path) -> pathlib.Path:
    """Create a directory at the config path so open() raises IsADirectoryError."""
    cfg_path = tmp_path / "lancet.json"
    cfg_path.mkdir()
    return cfg_path


def setup_existing_file(tmp_path: pathlib.Path) -> pathlib.Path:
    """Create a normal file at the config path; OSError will come from a patched open()."""
    cfg_path = tmp_path / "unreadable.json"
    cfg_path.write_text("{}", encoding="utf-8")
    return cfg_path


OSERROR_SCENARIOS: dict[str, OSErrorScenario] = {
    "permission_denied_via_patched_open": OSErrorScenario(
        setup=setup_existing_file,
        patch_open=True,
    ),
    "is_a_directory_at_config_path": OSErrorScenario(
        setup=setup_directory_at_cfg_path,
        patch_open=False,
    ),
}


def install_oserror_scenario(
    scenario: OSErrorScenario, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> pathlib.Path:
    """Apply the scenario's filesystem setup and (if requested) patched open(), return cfg_path."""
    cfg_path = scenario.setup(tmp_path)
    monkeypatch.setattr("lancet.config.CFG_PATH", cfg_path)
    if scenario.patch_open:
        monkeypatch.setattr("builtins.open", functools.partial(permission_denied_open, builtins.open, cfg_path))
    return cfg_path


class TestConfigReadFromFileOSError:
    """OSError from open() must be wrapped as ConfigReadError so read_config_file can recover."""

    @pytest.mark.parametrize("scenario", OSERROR_SCENARIOS.values(), ids=OSERROR_SCENARIOS.keys())
    def test_oserror_raises_config_read_error(
        self, scenario: OSErrorScenario, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
    ) -> None:
        """OSError variants from open() are wrapped as ConfigReadError."""
        install_oserror_scenario(scenario, monkeypatch, tmp_path)

        with pytest.raises(ConfigReadError):
            Config.read_from_file()

    @pytest.mark.parametrize("scenario", OSERROR_SCENARIOS.values(), ids=OSERROR_SCENARIOS.keys())
    def test_read_config_file_recovers(
        self, scenario: OSErrorScenario, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
    ) -> None:
        """read_config_file recovers from OSError at the open() layer for every scenario."""
        install_oserror_scenario(scenario, monkeypatch, tmp_path)

        result = read_config_file()
        assert isinstance(result.cfg, Config)
        assert result.error != ""


class DependencyVersionScenario(typing.NamedTuple):
    """A scenario for logging the installed transformers version."""

    version_side_effect: str | Exception
    expected_logger: str
    expected_substring: str


DEPENDENCY_VERSION_SCENARIOS: dict[str, DependencyVersionScenario] = {
    "transformers_installed": DependencyVersionScenario(
        version_side_effect="5.13.0",
        expected_logger="info",
        expected_substring="Using transformers 5.13.0",
    ),
    "transformers_missing": DependencyVersionScenario(
        version_side_effect=importlib.metadata.PackageNotFoundError("transformers"),
        expected_logger="warning",
        expected_substring="transformers is not installed",
    ),
}


class TestLogDependencyVersions:
    """log_dependency_versions records dependency versions useful for support reports."""

    @pytest.mark.parametrize("scenario", DEPENDENCY_VERSION_SCENARIOS.values(), ids=DEPENDENCY_VERSION_SCENARIOS.keys())
    def test_logs_transformers_version(
        self, scenario: DependencyVersionScenario, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        version = Mock()
        if isinstance(scenario.version_side_effect, Exception):
            version.side_effect = scenario.version_side_effect
        else:
            version.return_value = scenario.version_side_effect
        message = Mock()
        monkeypatch.setattr("lancet.__main__.importlib.metadata.version", version)
        monkeypatch.setattr(f"lancet.__main__.logger.{scenario.expected_logger}", message)

        log_dependency_versions()

        assert version.call_args.args == ("transformers",)
        assert message.call_args.args == (scenario.expected_substring,)


class CliScenario(typing.NamedTuple):
    """A CLI command method and the IPC-client method it must invoke."""

    method_name: str
    args: Sequence[object]
    client_method_name: str


CLI_SCENARIOS: dict[str, CliScenario] = {
    "screenshot": CliScenario("screenshot", (), "ask_screenshot"),
    "ocr": CliScenario("ocr", (False,), "ask_ocr"),
    "detect_and_ocr": CliScenario("ocr", (True,), "ask_ocr"),
}


class TestCliCommands:
    """Test CLI convenience methods delegate to their corresponding IPC-client methods."""

    @pytest.mark.parametrize("scenario", CLI_SCENARIOS.values(), ids=CLI_SCENARIOS.keys())
    def test_command(self, scenario: CliScenario, monkeypatch: pytest.MonkeyPatch) -> None:
        """Each CLI command logs the response returned by its matching client method."""
        response = IpcResponse(status=IpcStatus.ok, message="accepted")
        client = create_autospec(LancetIpcClient, instance=True)
        getattr(client, scenario.client_method_name).return_value = response
        cli = CLI(Config(), client)
        info = Mock()
        monkeypatch.setattr("lancet.__main__.logger.info", info)

        getattr(cli, scenario.method_name)(*scenario.args)

        if scenario.client_method_name == "ask_ocr":
            assert getattr(client, scenario.client_method_name).call_args.kwargs == {"detect": scenario.args[0]}
        else:
            assert getattr(client, scenario.client_method_name).call_args.args == scenario.args
        assert info.call_args.args == ("ok: accepted",)
