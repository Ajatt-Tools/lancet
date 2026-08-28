# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
import functools
import ntpath
import os
import pathlib
import posixpath
import shutil
import subprocess
import sys
from collections.abc import Sequence

from lancet.consts import IS_WIN


@functools.cache
def default_hardcoded_paths() -> Sequence[pathlib.Path]:
    """Return common executable directories used after PATH lookup fails."""
    return (
        pathlib.Path("/usr/bin"),
        pathlib.Path("/opt/homebrew/bin"),
        pathlib.Path("/usr/local/bin"),
        pathlib.Path("/bin"),
        pathlib.Path.home() / ".local" / "bin",
    )


def windows_executable_suffixes() -> Sequence[str]:
    """Return executable suffixes from PATHEXT when running on Windows."""
    if IS_WIN:
        path_extensions = os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD").split(";")
        return tuple(suffix.lower() for suffix in path_extensions if suffix)
    raise RuntimeError("not running Windows")


def is_executable_file(path: pathlib.Path) -> bool:
    """Return True if path points to an executable file."""
    if not path.is_file():
        return False
    if IS_WIN:
        return path.suffix.lower() in windows_executable_suffixes()
    return os.access(path, os.X_OK)


def executable_file_candidates(path_to_dir: pathlib.Path, name: str) -> Sequence[pathlib.Path]:
    """Return possible executable paths for name inside path_to_dir on the current platform."""
    path = path_to_dir / name
    if not IS_WIN or path.suffix:
        return (path,)
    return tuple(path.with_suffix(suffix) for suffix in windows_executable_suffixes())


def find_executable_hardcoded(name: str) -> str | None:
    """Search for an executable by name in a list of common installation directories."""
    for path_to_dir in default_hardcoded_paths():
        for path_to_exe in executable_file_candidates(path_to_dir, name):
            if is_executable_file(path_to_exe):
                return str(path_to_exe.resolve())
    return None


@functools.cache
def find_executable(name: str) -> str | None:
    """
    Resolve name to an executable path: absolute/~ path, then PATH, then hardcoded dirs.
    """
    path = pathlib.Path(name).expanduser()
    if path.is_absolute() and is_executable_file(path):
        return str(path.resolve())
    return shutil.which(name) or find_executable_hardcoded(name)


def resolve_executable_with_fallbacks(*fallback_names: str) -> str:
    """Return the first resolvable executable name, or an empty string."""
    for executable_name in fallback_names:
        name = executable_name.strip()
        if name and (resolved := find_executable(name)):
            return resolved
    return ""


def is_running_frozen() -> bool:
    """
    Frozen usually means running a binary created by pyinstaller.
    """
    return bool(getattr(sys, "frozen", False))


def normalize_env_path(path: str) -> str:
    """Normalize an environment path for platform-appropriate comparison."""
    if IS_WIN:
        return ntpath.normcase(ntpath.normpath(path))
    return posixpath.normpath(path)


def common_env_path(paths: Sequence[str]) -> str:
    """Return the longest common subpath using the active platform's path rules."""
    if IS_WIN:
        return ntpath.commonpath(paths)
    return posixpath.commonpath(paths)


def is_pyinstaller_path(path: str) -> bool:
    """Return True if path is the active PyInstaller extraction directory or one of its descendants."""
    if not (extraction_dir := getattr(sys, "_MEIPASS", "")):
        return False
    normalized_path = normalize_env_path(path)
    normalized_root = normalize_env_path(str(extraction_dir))
    try:
        return common_env_path((normalized_path, normalized_root)) == normalized_root
    except ValueError:
        return False


def filter_pyinstaller_paths(path_str: str) -> list[str]:
    """
    PyInstaller prepends to the original LD_LIBRARY_PATH and QT_PLUGIN_PATH values:
    LD_LIBRARY_PATH=/tmp/_MEIz10LqR
    QT_PLUGIN_PATH=/tmp/_MEIz10LqR/PyQt6/Qt6/plugins
    Remove PyInstaller's temporary extraction paths from the passed env var while preserving the user's original paths.
    """
    return [path for path in path_str.split(os.pathsep) if path.strip() and not is_pyinstaller_path(path)]


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

        # On Windows, PyInstaller prepends its extraction directory to PATH for bundled DLL lookup.
        # External Qt apps should not inherit that path, or they can load Lancet's bundled Qt DLLs/plugins.
        if IS_WIN:
            env = clean_ld_library_path(env, env_key="PATH")

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
