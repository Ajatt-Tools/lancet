# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import os
import sys

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
            ("", [""]),
            # Single path (no colons)
            ("/usr/lib", ["/usr/lib"]),
        ],
    )
    def test_filter_pyinstaller_paths(self, input_path: str, expected: list[str]) -> None:
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


class TestMakeCleanEnv:
    """Test environment cleaning for frozen binaries."""

    def test_make_clean_env_not_frozen(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that make_clean_env returns None when not running as frozen binary."""
        monkeypatch.delattr(sys, "frozen", raising=False)
        assert make_clean_env() is None

    def test_make_clean_env_frozen_removes_pyinstaller_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that make_clean_env removes PyInstaller-specific environment variables."""
        # Simulate frozen binary
        monkeypatch.setattr(sys, "frozen", True, raising=False)

        # Set up environment with PyInstaller variables
        test_env = {
            "PATH": "/usr/bin",
            "HOME": "/home/user",
            "LD_LIBRARY_PATH": "/tmp/_MEIxxxxx:/usr/lib",
            "QT_PLUGIN_PATH": "/tmp/_MEIxxxxx/PyQt6/Qt6/plugins",
            "QT_QPA_PLATFORM_PLUGIN_PATH": "/tmp/_MEIxxxxx/platforms",
            "PYTHONPATH": "/tmp/_MEIxxxxx",
            "PYTHONHOME": "/tmp/_MEIxxxxx",
        }
        monkeypatch.setattr(os, "environ", test_env)

        result = make_clean_env()

        assert result is not None
        assert result["PATH"] == "/usr/bin"
        assert result["HOME"] == "/home/user"
        assert result["LD_LIBRARY_PATH"] == "/usr/lib"  # PyInstaller path removed
        assert "QT_PLUGIN_PATH" not in result
        assert "QT_QPA_PLATFORM_PLUGIN_PATH" not in result
        assert "PYTHONPATH" not in result
        assert "PYTHONHOME" not in result

    def test_make_clean_env_frozen_preserves_user_ld_library_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that make_clean_env preserves user's original LD_LIBRARY_PATH."""
        monkeypatch.setattr(sys, "frozen", True, raising=False)

        test_env = {
            "PATH": "/usr/bin",
            "LD_LIBRARY_PATH": "/tmp/_MEIxxxxx:/opt/custom/lib:/usr/local/lib",
            "QT_PLUGIN_PATH": "/tmp/_MEIxxxxx/PyQt6/Qt6/plugins:/opt/custom/plugins:/usr/local/plugins",
        }
        monkeypatch.setattr(os, "environ", test_env)

        result = make_clean_env()

        assert result is not None
        assert result["LD_LIBRARY_PATH"] == "/opt/custom/lib:/usr/local/lib"
        assert result["QT_PLUGIN_PATH"] == "/opt/custom/plugins:/usr/local/plugins"
        assert result["PATH"] == "/usr/bin"

    def test_make_clean_env_frozen_removes_ld_library_path_if_only_pyinstaller(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that make_clean_env removes LD_LIBRARY_PATH if it only contains PyInstaller paths."""
        monkeypatch.setattr(sys, "frozen", True, raising=False)

        test_env = {
            "PATH": "/usr/bin",
            "LD_LIBRARY_PATH": "/tmp/_MEIxxxxx",
        }
        monkeypatch.setattr(os, "environ", test_env)

        result = make_clean_env()

        assert result is not None
        assert "LD_LIBRARY_PATH" not in result

    def test_make_clean_env_frozen_no_ld_library_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that make_clean_env works when LD_LIBRARY_PATH is not set."""
        monkeypatch.setattr(sys, "frozen", True, raising=False)

        test_env = {
            "PATH": "/usr/bin",
            "HOME": "/home/user",
        }
        monkeypatch.setattr(os, "environ", test_env)

        result = make_clean_env()

        assert result is not None
        assert result["PATH"] == "/usr/bin"
        assert result["HOME"] == "/home/user"
        assert "LD_LIBRARY_PATH" not in result
