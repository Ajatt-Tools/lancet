# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
import functools
import os
import shutil
import subprocess
from typing import Sequence

HARDCODED_PATHS = (
    "/usr/bin",
    "/opt/homebrew/bin",
    "/usr/local/bin",
    "/bin",
    os.path.join(os.getenv("HOME", "/home/user"), ".local", "bin"),
)


def find_executable_hardcoded(name: str) -> str | None:
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


def run_and_disown(args: Sequence[str]) -> None:
    subprocess.Popen(
        args,
        shell=False,
        start_new_session=True,
    )
