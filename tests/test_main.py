# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Tests for config recovery, CLI commands, and application startup dispatch."""

import builtins
import functools
import importlib.metadata
import json
import pathlib
import typing
from collections.abc import Callable, Sequence
from unittest.mock import MagicMock, Mock, call, create_autospec

import pytest

import lancet.__main__ as lancet_main
from lancet.cli import CLI, log_dependency_versions
from lancet.config import Config, ConfigFileReadResult, OcrDestination, read_config_file
from lancet.exceptions import ConfigReadError, PortAlreadyInUseError
from lancet.ipc.client import LancetIpcClient
from lancet.ipc.server import IpcServer
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
    expected_error_prefix: str  # Empty means no error expected.
    expected_copy_to: OcrDestination
    expect_backup: bool


RECOVERY_SCENARIOS: dict[str, ReadRecoveryScenario] = {
    "happy_path_returns_config": ReadRecoveryScenario(
        file_content=json.dumps({"copy_to": "clipboard"}),
        expected_error_prefix="",
        expected_copy_to=OcrDestination.clipboard,
        expect_backup=False,
    ),
    "missing_file_returns_defaults": ReadRecoveryScenario(
        file_content=None,
        expected_error_prefix="",
        expected_copy_to=OcrDestination.goldendict,
        expect_backup=False,
    ),
    "malformed_json_returns_defaults_with_error": ReadRecoveryScenario(
        file_content="{not valid json",
        expected_error_prefix="failed to decode json config file",
        expected_copy_to=OcrDestination.goldendict,
        expect_backup=True,
    ),
    "unknown_field_returns_defaults_with_error": ReadRecoveryScenario(
        file_content=json.dumps({"unknown_field": "value"}),
        expected_error_prefix="failed to parse config file",
        expected_copy_to=OcrDestination.goldendict,
        expect_backup=True,
    ),
    "non_object_json_returns_defaults_with_error": ReadRecoveryScenario(
        file_content="[]",
        expected_error_prefix="failed to parse config file: top-level JSON value must be an object",
        expected_copy_to=OcrDestination.goldendict,
        expect_backup=True,
    ),
    "unhashable_copy_to_uses_default": ReadRecoveryScenario(
        file_content=json.dumps({"copy_to": []}),
        expected_error_prefix="",
        expected_copy_to=OcrDestination.goldendict,
        expect_backup=False,
    ),
    "wrong_goldendict_path_type_returns_defaults_with_error": ReadRecoveryScenario(
        file_content=json.dumps({"path_to_goldendict_executable": {}}),
        expected_error_prefix="failed to parse config file",
        expected_copy_to=OcrDestination.goldendict,
        expect_backup=True,
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
    def test_recovery(
        self, scenario: ReadRecoveryScenario, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
    ) -> None:
        """Return a Config result with the expected value, error, and backup behavior."""
        cfg_path = write_scenario_config(scenario, tmp_path)
        monkeypatch.setattr("lancet.config.CFG_PATH", cfg_path)

        result = read_config_file()
        assert isinstance(result, ConfigFileReadResult)
        assert isinstance(result.cfg, Config)
        assert result.cfg.copy_to == scenario.expected_copy_to
        if scenario.expected_error_prefix:
            assert result.error.startswith(scenario.expected_error_prefix)
        else:
            assert result.error == ""
        assert cfg_path.with_suffix(".old").is_file() == scenario.expect_backup
        if scenario.expect_backup:
            assert cfg_path.is_file() is False


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
        """Log the installed version or a warning when transformers is absent."""
        version = Mock()
        if isinstance(scenario.version_side_effect, Exception):
            version.side_effect = scenario.version_side_effect
        else:
            version.return_value = scenario.version_side_effect
        message = Mock()
        monkeypatch.setattr("lancet.cli.importlib.metadata.version", version)
        monkeypatch.setattr(f"lancet.cli.logger.{scenario.expected_logger}", message)

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
        monkeypatch.setattr("lancet.cli.logger.info", info)

        getattr(cli, scenario.method_name)(*scenario.args)

        if scenario.client_method_name == "ask_ocr":
            assert getattr(client, scenario.client_method_name).call_args.kwargs == {"detect": scenario.args[0]}
        else:
            assert getattr(client, scenario.client_method_name).call_args.args == scenario.args
        assert info.call_args.args == ("ok: accepted",)


class MainDispatchScenario(typing.NamedTuple):
    """Expected entry-point dispatch for one command-line argument list."""

    args: Sequence[str]
    uses_cli: bool
    config_exists: bool = True
    port_in_use: bool = False
    config_error: str = ""


MAIN_DISPATCH_SCENARIOS: dict[str, MainDispatchScenario] = {
    "no_arguments_starts_gui": MainDispatchScenario((), False),
    "cli_saves_missing_config": MainDispatchScenario(("ocr",), True, False),
    "occupied_port_skips_gui": MainDispatchScenario((), False, True, True),
    "config_error_logs_and_starts_gui": MainDispatchScenario((), False, True, False, "invalid config"),
}


class MainDispatchHarness(typing.NamedTuple):
    """Mocks used to verify one main-entry-point dispatch."""

    cfg: Config
    result: ConfigFileReadResult
    cli: CLI
    cli_type: Mock
    fire: Mock
    entered_ipc: IpcServer
    ipc_context: MagicMock
    ipc_type: Mock
    run_program: Mock
    warning: Mock
    save_config: Mock
    setup_frozen: Mock
    log_versions: Mock
    read_config: Mock
    error_log: Mock


class MainConfigHarness(typing.NamedTuple):
    """Config state and persistence mock for one main dispatch."""

    cfg: Config
    result: ConfigFileReadResult
    save_config: Mock


class MainIpcHarness(typing.NamedTuple):
    """IPC context mocks for one main dispatch."""

    entered: IpcServer
    context: MagicMock
    ipc_type: Mock
    run_program: Mock


def make_main_config_harness(scenario: MainDispatchScenario) -> MainConfigHarness:
    """Create Config state for one dispatch scenario."""
    cfg = create_autospec(Config, instance=True)
    cfg.file_exists.return_value = scenario.config_exists
    return MainConfigHarness(cfg, ConfigFileReadResult(cfg, error=scenario.config_error), Mock())


def make_main_ipc_harness(scenario: MainDispatchScenario) -> MainIpcHarness:
    """Create IPC context state for one dispatch scenario."""
    entered_ipc = create_autospec(IpcServer, instance=True)
    ipc_context = MagicMock()
    ipc_context.__enter__.return_value = entered_ipc
    if scenario.port_in_use:
        ipc_context.__enter__.side_effect = PortAlreadyInUseError("port occupied")
    ipc_type, run_program = Mock(return_value=ipc_context), Mock()
    return MainIpcHarness(entered_ipc, ipc_context, ipc_type, run_program)


def assemble_main_dispatch_harness(
    config: MainConfigHarness, ipc: MainIpcHarness, cli: CLI, cli_type: Mock, fire: Mock
) -> MainDispatchHarness:
    """Assemble grouped collaborators into the assertion harness."""
    return MainDispatchHarness(
        config.cfg,
        config.result,
        cli,
        cli_type,
        fire,
        ipc.entered,
        ipc.context,
        ipc.ipc_type,
        ipc.run_program,
        Mock(),
        config.save_config,
        Mock(),
        Mock(),
        Mock(return_value=config.result),
        Mock(),
    )


def make_main_dispatch_harness(scenario: MainDispatchScenario) -> MainDispatchHarness:
    """Construct entry-point collaborators without installing patches."""
    config = make_main_config_harness(scenario)
    ipc = make_main_ipc_harness(scenario)
    cli = create_autospec(CLI, instance=True)
    return assemble_main_dispatch_harness(config, ipc, cli, Mock(return_value=cli), Mock())


def install_main_dispatch_patches(
    harness: MainDispatchHarness, scenario: MainDispatchScenario, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Install one harness as the entry point's collaborators."""
    monkeypatch.setattr(lancet_main.sys, "argv", ["lancet", *scenario.args])
    monkeypatch.setattr(lancet_main, "setup_frozen_binary", harness.setup_frozen)
    monkeypatch.setattr(lancet_main, "log_dependency_versions", harness.log_versions)
    monkeypatch.setattr(harness.cfg, "save_to_file", harness.save_config)
    monkeypatch.setattr(lancet_main, "read_config_file", harness.read_config)
    monkeypatch.setattr(lancet_main, "CLI", harness.cli_type)
    monkeypatch.setattr(lancet_main.fire, "Fire", harness.fire)
    monkeypatch.setattr(lancet_main, "IpcServer", harness.ipc_type)
    monkeypatch.setattr(lancet_main, "run_program", harness.run_program)
    monkeypatch.setattr(lancet_main.logger, "warning", harness.warning)
    monkeypatch.setattr(lancet_main.logger, "error", harness.error_log)


def install_main_dispatch(scenario: MainDispatchScenario, monkeypatch: pytest.MonkeyPatch) -> MainDispatchHarness:
    """Construct and install entry-point collaborators."""
    harness = make_main_dispatch_harness(scenario)
    install_main_dispatch_patches(harness, scenario, monkeypatch)
    return harness


class TestMainDispatch:
    """Test selection between CLI and GUI entry points."""

    @pytest.mark.parametrize("scenario", MAIN_DISPATCH_SCENARIOS.values(), ids=MAIN_DISPATCH_SCENARIOS.keys())
    def test_dispatches_by_arguments(self, scenario: MainDispatchScenario, monkeypatch: pytest.MonkeyPatch) -> None:
        """Arguments invoke Fire; an empty argument list enters the IPC-backed GUI."""
        harness = install_main_dispatch(scenario, monkeypatch)
        lancet_main.main()
        harness.setup_frozen.assert_called_once_with()
        harness.log_versions.assert_called_once_with()
        harness.read_config.assert_called_once_with()
        assert harness.cli_type.call_args_list == ([call(harness.cfg)] if scenario.uses_cli else [])
        assert harness.fire.call_args_list == ([call(harness.cli)] if scenario.uses_cli else [])
        assert harness.save_config.call_count == int(not scenario.config_exists)
        assert harness.ipc_type.call_args_list == ([] if scenario.uses_cli else [call(harness.cfg)])
        expected_run = (
            [call(harness.result, harness.entered_ipc)] if not (scenario.uses_cli or scenario.port_in_use) else []
        )
        assert harness.run_program.call_args_list == expected_run
        assert harness.ipc_context.__exit__.call_count == int(not (scenario.uses_cli or scenario.port_in_use))
        assert harness.warning.call_args_list == ([call("port occupied")] if scenario.port_in_use else [])
        assert harness.error_log.call_args_list == ([call(scenario.config_error)] if scenario.config_error else [])
