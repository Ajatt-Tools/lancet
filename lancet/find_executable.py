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


def make_clean_env() -> dict[str, str] | None:
    """
    Clean environment for frozen binaries to prevent library conflicts with external Qt applications.
    Without this, GoldenDict fails to start when running the Lancet binary produced by pyinstaller.
    """
    env = None
    if is_running_frozen():
        env = os.environ.copy()
        # Remove PyInstaller-specific environment variables that cause Qt version conflicts
        env.pop("LD_LIBRARY_PATH", None)
        # Remove Qt plugin paths that might conflict
        env.pop("QT_PLUGIN_PATH", None)
        env.pop("QT_QPA_PLATFORM_PLUGIN_PATH", None)
        # Also remove Python-specific variables (not needed for external programs)
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
