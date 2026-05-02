# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import os
import sys
import typing
from collections.abc import Sequence

import pytest

from lancet.find_executable import clean_ld_library_path, filter_pyinstaller_paths, make_clean_env


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
