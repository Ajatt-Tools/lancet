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
    executable_file_candidates,
    filter_pyinstaller_paths,
    find_executable,
    find_executable_hardcoded,
    is_executable_file,
    is_pyinstaller_path,
    make_clean_env,
    normalize_env_path,
    resolve_executable_with_fallbacks,
)


@pytest.fixture()
def windows_pathsep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch os.pathsep to semicolon to simulate Windows PATH-style separators."""
    monkeypatch.setattr("lancet.find_executable.os.pathsep", ";")


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
            # Repeated PyInstaller paths
            ("/tmp/_MEIxxxxx:/usr/lib:/tmp/_MEIxxxxx/lib:/opt/lib", ["/usr/lib", "/opt/lib"]),
            # A similarly named user path must be preserved
            ("/opt/_MEI-tools/lib:/usr/lib", ["/opt/_MEI-tools/lib", "/usr/lib"]),
            # Empty string
            ("", []),
            # Single path (no colons)
            ("/usr/lib", ["/usr/lib"]),
        ],
    )
    def test_filter_pyinstaller_paths(
        self, input_path: str, expected: Sequence[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that PyInstaller paths are correctly filtered out."""
        monkeypatch.setattr(sys, "_MEIPASS", "/tmp/_MEIxxxxx", raising=False)
        assert filter_pyinstaller_paths(input_path) == expected

    def test_filter_windows_paths(self, windows_pathsep: None, monkeypatch: pytest.MonkeyPatch) -> None:
        """Windows PATH-style separators are handled when os.pathsep is semicolon."""
        monkeypatch.setattr(sys, "_MEIPASS", r"C:\Users\user\AppData\Local\Temp\_MEIxxxxx", raising=False)
        monkeypatch.setattr("lancet.find_executable.IS_WIN", True)
        assert filter_pyinstaller_paths(r"C:\Users\user\AppData\Local\Temp\_MEIxxxxx;C:\Qt\plugins") == [
            r"C:\Qt\plugins"
        ]


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
                {"LD_LIBRARY_PATH": "/tmp/_MEIxxxxx:/usr/lib:/tmp/_MEIxxxxx/lib", "PATH": "/usr/bin"},
                {"LD_LIBRARY_PATH": "/usr/lib", "PATH": "/usr/bin"},
            ),
        ],
    )
    def test_clean_ld_library_path(
        self, input_env: dict[str, str], expected_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that LD_LIBRARY_PATH is correctly cleaned in environment dictionary."""
        monkeypatch.setattr(sys, "_MEIPASS", "/tmp/_MEIxxxxx", raising=False)
        result = clean_ld_library_path(input_env.copy())
        assert result == expected_env

    def test_clean_windows_path_variable(self, windows_pathsep: None, monkeypatch: pytest.MonkeyPatch) -> None:
        """Windows PATH-style separators are preserved when cleaning PATH-like variables."""
        monkeypatch.setattr(sys, "_MEIPASS", r"C:\Temp\_MEIaaa", raising=False)
        monkeypatch.setattr("lancet.find_executable.IS_WIN", True)
        result = clean_ld_library_path(
            {"QT_PLUGIN_PATH": r"C:\Temp\_MEIaaa;C:\Qt\plugins", "PATH": r"C:\Windows"},
            env_key="QT_PLUGIN_PATH",
        )
        assert result == {"QT_PLUGIN_PATH": r"C:\Qt\plugins", "PATH": r"C:\Windows"}


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

    @pytest.mark.parametrize("scenario", FROZEN_SCENARIOS.values(), ids=FROZEN_SCENARIOS.keys())
    def test_make_clean_env_frozen(self, scenario: MakeCleanEnvScenario, monkeypatch: pytest.MonkeyPatch) -> None:
        """For each frozen-binary scenario, verify the cleaned env matches expectations."""
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "_MEIPASS", "/tmp/_MEIxxxxx", raising=False)
        monkeypatch.setattr(os, "environ", dict(scenario.input_env))

        result = make_clean_env()
        assert result is not None

        for key, expected_value in scenario.expected.items():
            if expected_value is None:
                assert key not in result
            else:
                assert result[key] == expected_value


class TestIsPyinstallerPath:
    """Test platform-independent PyInstaller extraction path detection."""

    @pytest.mark.parametrize(
        "path,expected",
        [
            ("/tmp/_MEIxxxxx", True),
            ("/tmp/_MEIxxxxx/PyQt6/Qt6/plugins", True),
            ("/tmp//_MEIxxxxx/./PyQt6", True),
            ("/tmp/_MEIxxxxx/../other", False),
            ("/tmp/_MEIxxxxx-other", False),
            ("tmp/_MEIxxxxx", False),
            ("/opt/_MEI-tools/lib", False),
            ("/usr/lib", False),
        ],
    )
    def test_detect(self, path: str, expected: bool, monkeypatch: pytest.MonkeyPatch) -> None:
        """is_pyinstaller_path recognizes only the active extraction root and descendants."""
        monkeypatch.setattr(sys, "_MEIPASS", "/tmp/_MEIxxxxx", raising=False)
        assert is_pyinstaller_path(path) is expected

    @pytest.mark.parametrize(
        "path,expected",
        [
            (r"c:\temp\_meixxxxx", True),
            (r"C:\TEMP\_MEIXXXXX\PyQt6", True),
            (r"C:\Temp\_MEIxxxxx\plugins\..\platforms", True),
            (r"C:\Temp\_MEIxxxxx-other", False),
            (r"C:\Temp\_MEI-tools", False),
            (r"D:\Temp\_MEIxxxxx", False),
        ],
    )
    def test_detect_windows_case_insensitive(self, path: str, expected: bool, monkeypatch: pytest.MonkeyPatch) -> None:
        """Windows extraction-root matching is case-insensitive."""
        monkeypatch.setattr(sys, "_MEIPASS", r"C:\Temp\_MEIxxxxx", raising=False)
        monkeypatch.setattr("lancet.find_executable.IS_WIN", True)
        assert is_pyinstaller_path(path) is expected

    @pytest.mark.parametrize("path", ["/tmp/_MEIxxxxx"])
    def test_without_extraction_dir(self, path: str, monkeypatch: pytest.MonkeyPatch) -> None:
        """No path is classified as PyInstaller-owned when _MEIPASS is unavailable."""
        monkeypatch.delattr(sys, "_MEIPASS", raising=False)
        assert is_pyinstaller_path(path) is False


class TestNormalizeEnvPath:
    """Test platform-specific environment path normalization."""

    @pytest.mark.parametrize(
        "is_windows,path,expected",
        [
            (False, "/tmp/example/", "/tmp/example"),
            (False, "/tmp/example/./plugins/../lib", "/tmp/example/lib"),
            (False, r"/tmp/example\name/", r"/tmp/example\name"),
            (True, "C:\\Temp\\Example\\", r"c:\temp\example"),
            (True, r"C:\Temp\Example\.\plugins\..\lib", r"c:\temp\example\lib"),
        ],
    )
    def test_normalize(self, is_windows: bool, path: str, expected: str, monkeypatch: pytest.MonkeyPatch) -> None:
        """Separators, trailing slashes, and Windows case are normalized."""
        monkeypatch.setattr("lancet.find_executable.IS_WIN", is_windows)
        assert normalize_env_path(path) == expected


class TestIsExecutableFile:
    """Test executable file detection."""

    @pytest.mark.parametrize("mode,expected", [(0o755, True), (0o644, False)])
    def test_file_mode(self, mode: int, expected: bool, tmp_path: pathlib.Path) -> None:
        """Only executable regular files are accepted."""
        file_path = tmp_path / "probe"
        file_path.write_text("#!/bin/sh\n", encoding="utf-8")
        file_path.chmod(mode)
        assert is_executable_file(file_path) is expected

    @pytest.mark.parametrize("suffix,expected", [(".exe", True), (".txt", False)])
    def test_windows_file_type(
        self, suffix: str, expected: bool, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
    ) -> None:
        """Windows executable detection uses the filename suffix instead of POSIX mode bits."""
        monkeypatch.setattr("lancet.find_executable.IS_WIN", True)
        file_path = tmp_path / f"probe{suffix}"
        file_path.write_text("contents", encoding="utf-8")
        assert is_executable_file(file_path) is expected


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
    """Replace default_hardcoded_paths() with three tmp dirs and optionally create the named file."""
    search_dirs = (tmp_path / "bin1", tmp_path / "bin2", tmp_path / "bin3")
    for path_str in search_dirs:
        path_str.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("lancet.find_executable.default_hardcoded_paths", lambda: search_dirs)
    if scenario.place_in is not None:
        make_executable_file(tmp_path / scenario.place_in, scenario.name)


class FindExecutableScenario(typing.NamedTuple):
    """A scenario describing how find_executable falls back from PATH to default hardcoded paths."""

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
    """Wire PATH and default hardcoded paths to empty dirs, optionally creating the file in each."""
    path_dir = tmp_path / "path_dir"
    hardcoded_dir = tmp_path / "hardcoded_dir"
    path_dir.mkdir()
    hardcoded_dir.mkdir()

    monkeypatch.setattr(os, "environ", {"PATH": str(path_dir)})
    monkeypatch.setattr("lancet.find_executable.default_hardcoded_paths", lambda: (hardcoded_dir,))

    if scenario.on_path:
        make_executable_file(path_dir, name)
    if scenario.on_hardcoded:
        make_executable_file(hardcoded_dir, name)

    return path_dir, hardcoded_dir


class TestFindExecutable:
    """find_executable prefers PATH (via shutil.which) and falls back to default hardcoded paths."""

    @pytest.mark.parametrize("scenario", FIND_SCENARIOS.values(), ids=FIND_SCENARIOS.keys())
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

    @pytest.mark.parametrize("scenario", FIND_HARDCODED_SCENARIOS.values(), ids=FIND_HARDCODED_SCENARIOS.keys())
    def test_lookup_hardcoded(
        self,
        scenario: FindExecutableHardcodedScenario,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: pathlib.Path,
    ) -> None:
        """
        find_executable_hardcoded scans default hardcoded paths in order, returning the first hit.
        Each scenario verifies whether the name is resolved from the patched search dirs.
        """
        install_hardcoded_search_path(scenario, monkeypatch, tmp_path)
        result = find_executable_hardcoded(scenario.name)

        if scenario.expected_found:
            assert result is not None
            assert pathlib.Path(result).name == scenario.name
        else:
            assert result is None

    @pytest.mark.parametrize("mode,expected_found", [(0o755, True), (0o644, False)])
    def test_absolute_path(self, mode: int, expected_found: bool, tmp_path: pathlib.Path) -> None:
        """Absolute paths resolve only when they point to executable files."""
        executable = tmp_path / "custom-app"
        executable.write_text("#!/bin/sh\n", encoding="utf-8")
        executable.chmod(mode)
        result = find_executable(str(executable))
        if expected_found:
            assert result == str(executable.resolve())
        else:
            assert result is None

    def test_home_expanded_absolute_path(self, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
        """A configured ~/ path is expanded before executable checks."""
        bin_dir = tmp_path / "bin"
        executable = make_executable_file(bin_dir, "goldendict")
        monkeypatch.setenv("HOME", str(tmp_path))
        assert find_executable("~/bin/goldendict") == str(executable.resolve())

    def test_windows_hardcoded_lookup_adds_exe_suffix(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
    ) -> None:
        """A Windows hardcoded lookup resolves a bare browser name to its .exe file."""
        monkeypatch.setattr("lancet.find_executable.IS_WIN", True)
        monkeypatch.setattr("lancet.find_executable.default_hardcoded_paths", lambda: (tmp_path,))
        executable = tmp_path / "firefox.exe"
        executable.write_text("contents", encoding="utf-8")

        assert find_executable_hardcoded("firefox") == str(executable.resolve())


class ExecutableCandidatesScenario(typing.NamedTuple):
    """A platform/name combination and its expected executable candidate filenames."""

    is_windows: bool
    name: str
    suffixes: Sequence[str]
    expected_names: Sequence[str]


EXECUTABLE_CANDIDATE_SCENARIOS: dict[str, ExecutableCandidatesScenario] = {
    "non_windows_keeps_bare_name": ExecutableCandidatesScenario(False, "firefox", (), ("firefox",)),
    "windows_bare_name_uses_suffix_order": ExecutableCandidatesScenario(
        True, "firefox", (".cmd", ".exe"), ("firefox.cmd", "firefox.exe")
    ),
    "windows_explicit_suffix_is_preserved": ExecutableCandidatesScenario(
        True, "firefox.exe", (".cmd", ".exe"), ("firefox.exe",)
    ),
}


class TestExecutableFileCandidates:
    """Test platform-specific executable candidate generation."""

    @pytest.mark.parametrize(
        "scenario", EXECUTABLE_CANDIDATE_SCENARIOS.values(), ids=EXECUTABLE_CANDIDATE_SCENARIOS.keys()
    )
    def test_candidates(
        self, scenario: ExecutableCandidatesScenario, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
    ) -> None:
        """Candidate generation preserves explicit names and Windows suffix order."""
        monkeypatch.setattr("lancet.find_executable.IS_WIN", scenario.is_windows)
        monkeypatch.setattr("lancet.find_executable.windows_executable_suffixes", lambda: scenario.suffixes)

        candidates = executable_file_candidates(tmp_path, scenario.name)

        assert tuple(candidate.name for candidate in candidates) == scenario.expected_names


class ResolverScenario(typing.NamedTuple):
    """A scenario for resolve_executable_with_fallbacks."""

    executable_names: Sequence[str]
    available_name: str | None
    expected: str


RESOLVER_SCENARIOS: dict[str, ResolverScenario] = {
    "first_name_resolved": ResolverScenario(("custom", "fallback"), "custom", "/usr/bin/custom"),
    "later_name_resolved": ResolverScenario(("missing", "fallback"), "fallback", "/usr/bin/fallback"),
    "empty_name_skipped": ResolverScenario(("", "fallback"), "fallback", "/usr/bin/fallback"),
    "total_failure_empty": ResolverScenario(("missing", "fallback"), None, ""),
}


class TestResolveExecutableWithFallbacks:
    """Test shared executable resolution semantics."""

    @pytest.mark.parametrize("scenario", RESOLVER_SCENARIOS.values(), ids=RESOLVER_SCENARIOS.keys())
    def test_resolve(self, scenario: ResolverScenario, monkeypatch: pytest.MonkeyPatch) -> None:
        """Executable names are tried in order; an empty result signals total failure."""
        monkeypatch.setattr(
            "lancet.find_executable.find_executable",
            lambda name: f"/usr/bin/{name}" if name == scenario.available_name else None,
        )
        assert resolve_executable_with_fallbacks(*scenario.executable_names) == scenario.expected
