# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import os
import pathlib
import sys
import typing
from collections.abc import Iterator, Sequence

import pytest

from lancet.find_executable import (
    clean_ld_library_path,
    filter_pyinstaller_paths,
    find_executable,
    find_executable_hardcoded,
    make_clean_env,
)


class TestFilterPyinstallerPaths:
    """Test filtering of PyInstaller paths from LD_LIBRARY_PATH."""

    @pytest.mark.parametrize(
        "input_path,expected",
        [
            # No PyInstaller paths
            ("/usr/lib:/opt/lib", ["/usr/lib", "/opt/lib"]),
            # Only PyInstaller path
            ("/tmp/_MEIxxxxx", []),
            # PyInstaller path at start
            ("/tmp/_MEIxxxxx:/usr/lib:/opt/lib", ["/usr/lib", "/opt/lib"]),
            # PyInstaller path in middle
            ("/usr/lib:/tmp/_MEIxxxxx:/opt/lib", ["/usr/lib", "/opt/lib"]),
            # PyInstaller path at end
            ("/usr/lib:/opt/lib:/tmp/_MEIxxxxx", ["/usr/lib", "/opt/lib"]),
            # Multiple PyInstaller paths
            ("/tmp/_MEIaaa:/usr/lib:/tmp/_MEIbbb:/opt/lib", ["/usr/lib", "/opt/lib"]),
            # Empty string
            ("", []),
            # Single path (no colons)
            ("/usr/lib", ["/usr/lib"]),
        ],
    )
    def test_filter_pyinstaller_paths(self, input_path: str, expected: Sequence[str]) -> None:
        """Test that PyInstaller paths are correctly filtered out."""
        assert filter_pyinstaller_paths(input_path) == expected


class TestCleanLdLibraryPath:
    """Test cleaning of LD_LIBRARY_PATH in environment dictionary."""

    @pytest.mark.parametrize(
        "input_env,expected_env",
        [
            # No LD_LIBRARY_PATH
            ({"PATH": "/usr/bin"}, {"PATH": "/usr/bin"}),
            # LD_LIBRARY_PATH with user paths only
            (
                {"LD_LIBRARY_PATH": "/usr/lib:/opt/lib", "PATH": "/usr/bin"},
                {"LD_LIBRARY_PATH": "/usr/lib:/opt/lib", "PATH": "/usr/bin"},
            ),
            # LD_LIBRARY_PATH with PyInstaller path at start
            (
                {"LD_LIBRARY_PATH": "/tmp/_MEIxxxxx:/usr/lib", "PATH": "/usr/bin"},
                {"LD_LIBRARY_PATH": "/usr/lib", "PATH": "/usr/bin"},
            ),
            # LD_LIBRARY_PATH with only PyInstaller path (should be removed)
            (
                {"LD_LIBRARY_PATH": "/tmp/_MEIxxxxx", "PATH": "/usr/bin"},
                {"PATH": "/usr/bin"},
            ),
            # LD_LIBRARY_PATH with multiple PyInstaller paths
            (
                {"LD_LIBRARY_PATH": "/tmp/_MEIaaa:/usr/lib:/tmp/_MEIbbb", "PATH": "/usr/bin"},
                {"LD_LIBRARY_PATH": "/usr/lib", "PATH": "/usr/bin"},
            ),
        ],
    )
    def test_clean_ld_library_path(self, input_env: dict[str, str], expected_env: dict[str, str]) -> None:
        """Test that LD_LIBRARY_PATH is correctly cleaned in environment dictionary."""
        result = clean_ld_library_path(input_env.copy())
        assert result == expected_env


class MakeCleanEnvScenario(typing.NamedTuple):
    """A make_clean_env() frozen-binary test scenario.

    'input_env' is the simulated os.environ.
    'expected' lists the expectations on the returned dict:
    a string value means "key must be present and equal to this", and None means "key must be absent".
    """

    input_env: dict[str, str]
    expected: dict[str, str | None]


# Each scenario simulates a frozen binary with a specific environment shape and
# encodes both the values that must survive and the keys that must be removed.
FROZEN_SCENARIOS: dict[str, MakeCleanEnvScenario] = {
    "removes_pyinstaller_vars_and_cleans_ld_path": MakeCleanEnvScenario(
        input_env={
            "PATH": "/usr/bin",
            "HOME": "/home/user",
            "LD_LIBRARY_PATH": "/tmp/_MEIxxxxx:/usr/lib",
            "QT_PLUGIN_PATH": "/tmp/_MEIxxxxx/PyQt6/Qt6/plugins",
            "QT_QPA_PLATFORM_PLUGIN_PATH": "/tmp/_MEIxxxxx/platforms",
            "PYTHONPATH": "/tmp/_MEIxxxxx",
            "PYTHONHOME": "/tmp/_MEIxxxxx",
        },
        expected={
            "PATH": "/usr/bin",
            "HOME": "/home/user",
            "LD_LIBRARY_PATH": "/usr/lib",  # PyInstaller path removed
            "QT_PLUGIN_PATH": None,
            "QT_QPA_PLATFORM_PLUGIN_PATH": None,
            "PYTHONPATH": None,
            "PYTHONHOME": None,
        },
    ),
    "preserves_user_ld_library_path_and_qt_plugin_path": MakeCleanEnvScenario(
        input_env={
            "PATH": "/usr/bin",
            "LD_LIBRARY_PATH": "/tmp/_MEIxxxxx:/opt/custom/lib:/usr/local/lib",
            "QT_PLUGIN_PATH": "/tmp/_MEIxxxxx/PyQt6/Qt6/plugins:/opt/custom/plugins:/usr/local/plugins",
        },
        expected={
            "PATH": "/usr/bin",
            "LD_LIBRARY_PATH": "/opt/custom/lib:/usr/local/lib",
            "QT_PLUGIN_PATH": "/opt/custom/plugins:/usr/local/plugins",
        },
    ),
    "removes_ld_library_path_if_only_pyinstaller": MakeCleanEnvScenario(
        input_env={
            "PATH": "/usr/bin",
            "LD_LIBRARY_PATH": "/tmp/_MEIxxxxx",
        },
        expected={
            "PATH": "/usr/bin",
            "LD_LIBRARY_PATH": None,
        },
    ),
    "no_ld_library_path_set": MakeCleanEnvScenario(
        input_env={
            "PATH": "/usr/bin",
            "HOME": "/home/user",
        },
        expected={
            "PATH": "/usr/bin",
            "HOME": "/home/user",
            "LD_LIBRARY_PATH": None,
        },
    ),
}


class TestMakeCleanEnv:
    """Test environment cleaning for frozen binaries."""

    def test_make_clean_env_not_frozen(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """make_clean_env returns None when not running as a frozen binary."""
        monkeypatch.delattr(sys, "frozen", raising=False)
        assert make_clean_env() is None

    @pytest.mark.parametrize("scenario", FROZEN_SCENARIOS.values(), ids=list(FROZEN_SCENARIOS.keys()))
    def test_make_clean_env_frozen(self, scenario: MakeCleanEnvScenario, monkeypatch: pytest.MonkeyPatch) -> None:
        """For each frozen-binary scenario, verify the cleaned env matches expectations."""
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(os, "environ", dict(scenario.input_env))

        result = make_clean_env()
        assert result is not None

        for key, expected_value in scenario.expected.items():
            if expected_value is None:
                assert key not in result
            else:
                assert result[key] == expected_value


@pytest.fixture(autouse=True)
def clear_find_executable_cache() -> Iterator[None]:
    """Clear find_executable's lru_cache before and after every test in this module."""
    find_executable.cache_clear()
    yield
    find_executable.cache_clear()


def make_executable_file(directory: pathlib.Path, name: str) -> pathlib.Path:
    """Create an executable-marked file under directory and return its path."""
    directory.mkdir(parents=True, exist_ok=True)
    file_path = directory / name
    file_path.write_text("#!/bin/sh\n", encoding="utf-8")
    file_path.chmod(0o755)
    return file_path


class FindExecutableHardcodedScenario(typing.NamedTuple):
    """A scenario describing how find_executable_hardcoded resolves a name across hardcoded dirs."""

    place_in: str | None  # Subdirectory of tmp_path where the file is created; None means "create no file".
    name: str
    expected_found: bool


def install_hardcoded_search_path(
    scenario: FindExecutableHardcodedScenario,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    """Replace HARDCODED_PATHS with three tmp dirs and (if requested) materialise the named file."""
    search_dirs = (tmp_path / "bin1", tmp_path / "bin2", tmp_path / "bin3")
    for path_str in search_dirs:
        path_str.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("lancet.find_executable.HARDCODED_PATHS", tuple(str(s) for s in search_dirs))
    if scenario.place_in is not None:
        make_executable_file(tmp_path / scenario.place_in, scenario.name)


class FindExecutableScenario(typing.NamedTuple):
    """A scenario describing how find_executable falls back from PATH to HARDCODED_PATHS."""

    on_path: bool  # True if the executable should be created in a directory on PATH.
    on_hardcoded: bool  # True if the executable should be created in a hardcoded directory.
    expected_found: bool
    expected_in_path_dir: bool  # If found, must the result come from the PATH directory rather than the hardcoded one?


FIND_SCENARIOS: dict[str, FindExecutableScenario] = {
    "prefers_path_when_both_exist": FindExecutableScenario(
        on_path=True,
        on_hardcoded=True,
        expected_found=True,
        expected_in_path_dir=True,
    ),
    "falls_back_to_hardcoded_when_not_on_path": FindExecutableScenario(
        on_path=False,
        on_hardcoded=True,
        expected_found=True,
        expected_in_path_dir=False,
    ),
    "returns_none_when_neither": FindExecutableScenario(
        on_path=False,
        on_hardcoded=False,
        expected_found=False,
        expected_in_path_dir=False,
    ),
}
FIND_HARDCODED_SCENARIOS: dict[str, FindExecutableHardcodedScenario] = {
    "found_in_first_hardcoded_dir": FindExecutableHardcodedScenario(
        place_in="bin1",
        name="probe_one",
        expected_found=True,
    ),
    "found_in_later_hardcoded_dir": FindExecutableHardcodedScenario(
        place_in="bin2",
        name="probe_two",
        expected_found=True,
    ),
    "not_found_anywhere": FindExecutableHardcodedScenario(
        place_in=None,
        name="probe_missing",
        expected_found=False,
    ),
}


def install_find_executable_dirs(
    scenario: FindExecutableScenario,
    name: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> tuple[pathlib.Path, pathlib.Path]:
    """Wire PATH and HARDCODED_PATHS to two empty dirs, optionally materializing the file in each."""
    path_dir = tmp_path / "path_dir"
    hardcoded_dir = tmp_path / "hardcoded_dir"
    path_dir.mkdir()
    hardcoded_dir.mkdir()

    monkeypatch.setattr(os, "environ", {"PATH": str(path_dir)})
    monkeypatch.setattr("lancet.find_executable.HARDCODED_PATHS", (str(hardcoded_dir),))

    if scenario.on_path:
        make_executable_file(path_dir, name)
    if scenario.on_hardcoded:
        make_executable_file(hardcoded_dir, name)

    return path_dir, hardcoded_dir


class TestFindExecutable:
    """find_executable prefers PATH (via shutil.which) and falls back to HARDCODED_PATHS."""

    @pytest.mark.parametrize("scenario", FIND_SCENARIOS.values())
    def test_lookup(
        self,
        scenario: FindExecutableScenario,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: pathlib.Path,
    ) -> None:
        """
        Each scenario asserts presence/absence and which directory wins.
        """
        name = "find_probe"
        path_dir, hardcoded_dir = install_find_executable_dirs(scenario, name, monkeypatch, tmp_path)
        result = find_executable(name)

        if not scenario.expected_found:
            assert result is None
            return

        assert result is not None
        result_dir = pathlib.Path(result).parent
        if scenario.expected_in_path_dir:
            assert result_dir == path_dir
        else:
            assert result_dir == hardcoded_dir

    @pytest.mark.parametrize("scenario", FIND_HARDCODED_SCENARIOS.values())
    def test_lookup_hardcoded(
        self,
        scenario: FindExecutableHardcodedScenario,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: pathlib.Path,
    ) -> None:
        """
        find_executable_hardcoded scans HARDCODED_PATHS in order, returning the first hit.
        Each scenario verifies whether the name is resolved from the patched search dirs.
        """
        install_hardcoded_search_path(scenario, monkeypatch, tmp_path)
        result = find_executable_hardcoded(scenario.name)

        if scenario.expected_found:
            assert result is not None
            assert pathlib.Path(result).name == scenario.name
        else:
            assert result is None
