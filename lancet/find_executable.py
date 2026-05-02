# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
import functools
import os
import shutil
import subprocess
import sys
from collections.abc import Sequence

HARDCODED_PATHS = (
    "/usr/bin",
    "/opt/homebrew/bin",
    "/usr/local/bin",
    "/bin",
    os.path.join(os.getenv("HOME", "/home/user"), ".local", "bin"),
)


def find_executable_hardcoded(name: str) -> str | None:
    """Search for an executable by name in a list of common installation directories."""
    for path_to_dir in HARDCODED_PATHS:
        if os.path.isfile(path_to_exe := os.path.join(path_to_dir, name)):
            return path_to_exe
    return None


@functools.cache
def find_executable(name: str) -> str | None:
    """
    If possible, use the executable installed in the system.
    Otherwise, try fallback paths.
    """
    return shutil.which(name) or find_executable_hardcoded(name)


def is_running_frozen() -> bool:
    """
    Frozen usually means running a binary created by pyinstaller.
    """
    return bool(getattr(sys, "frozen", False))


def filter_pyinstaller_paths(path_str: str) -> list[str]:
    """
    PyInstaller prepends to the original LD_LIBRARY_PATH and QT_PLUGIN_PATH values:
    LD_LIBRARY_PATH=/tmp/_MEIz10LqR
    QT_PLUGIN_PATH=/tmp/_MEIz10LqR/PyQt6/Qt6/plugins
    Remove PyInstaller's temporary extraction paths from the passed env var while preserving the user's original paths.
    """
    return [path for path in path_str.split(os.pathsep) if path.strip() and not path.startswith("/tmp/_MEI")]


def clean_ld_library_path(env: dict[str, str], *, env_key: str = "LD_LIBRARY_PATH") -> dict[str, str]:
    """
    Restore original LD_LIBRARY_PATH (remove PyInstaller's prefix)
    """
    if env_key in env:
        if cleaned_parts := filter_pyinstaller_paths(env[env_key]):
            env[env_key] = os.pathsep.join(cleaned_parts)
        else:
            env.pop(env_key)
    return env


def make_clean_env() -> dict[str, str] | None:
    """
    Clean environment for frozen binaries to prevent library conflicts with external Qt applications.

    PyInstaller sets LD_LIBRARY_PATH and QT_PLUGIN_PATH to its extracted bundle,
    which causes external Qt applications (like GoldenDict) to crash
    when they try to load incompatible libraries/plugins.
    This function removes PyInstaller's paths while preserving the user's original LD_LIBRARY_PATH (if any).

    https://pyinstaller.org/en/stable/advanced-topics.html#bootloader
    """
    env = None
    if is_running_frozen():
        env = os.environ.copy()

        # Restore original LD_LIBRARY_PATH (remove PyInstaller's prefix)
        env = clean_ld_library_path(env, env_key="LD_LIBRARY_PATH")

        # Remove Qt plugin paths (these are always PyInstaller-specific)
        env = clean_ld_library_path(env, env_key="QT_PLUGIN_PATH")
        env = clean_ld_library_path(env, env_key="QT_QPA_PLATFORM_PLUGIN_PATH")

        # Remove Python-specific variables (not needed for external programs)
        env.pop("PYTHONPATH", None)
        env.pop("PYTHONHOME", None)
    return env


def run_and_disown(args: Sequence[str]) -> None:
    """Start a subprocess detached from the current process group so it survives application exit."""
    _ = subprocess.Popen(
        args,
        shell=False,
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=make_clean_env(),  # Use cleaned environment
    )
