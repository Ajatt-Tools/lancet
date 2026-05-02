# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
import os
import pathlib
import sys
import typing

P = typing.Final[pathlib.Path]
S = typing.Final[str]
B = typing.Final[bool]

APP_NAME: S = "Lancet"
THIS_DIR: P = pathlib.Path(__file__).resolve().parent
DESKTOP_FILE: P = THIS_DIR / f"{APP_NAME.lower()}.desktop"
ICONS_DIR: P = THIS_DIR / "icons"
APP_LOGO_PATH: P = ICONS_DIR / "app_logo.png"
SCREENSHOT_ICON_PATH: P = ICONS_DIR / "screenshot.png"
OCR_ICON_PATH: P = ICONS_DIR / "ocr.png"
EXIT_ICON_PATH: P = ICONS_DIR / "exit.png"
RESTART_ICON_PATH: P = ICONS_DIR / "restart.png"
PREFERENCES_ICON_PATH: P = ICONS_DIR / "preferences.png"
CFG_DIR_PATH: P = pathlib.Path(os.environ.get("XDG_CONFIG_HOME", pathlib.Path.home() / ".config")) / APP_NAME.lower()
CFG_PATH: P = CFG_DIR_PATH / f"{APP_NAME.lower()}.json"

CACHE_DIR_PATH: P = pathlib.Path(os.environ.get("XDG_CACHE_HOME", pathlib.Path.home() / ".cache")) / APP_NAME.lower()
HISTORY_FILE_PATH: P = CACHE_DIR_PATH / "ocr_history.json"
GEOMETRY_FILE_PATH: P = CACHE_DIR_PATH / "geometry"

IS_MAC: B = sys.platform.startswith("darwin")
IS_WIN: B = sys.platform.startswith("win32")

GITHUB_URL: S = "https://github.com/Ajatt-Tools/lancet"
CHAT_URL: S = "https://ajatt.top/blog/join-our-community.html"

DEFAULT_MODEL_NAME: S = "tatsumoto/manga-ocr-base"
OCR_JOIN_STR: S = " "


def self_check() -> None:
    for file in (
        DESKTOP_FILE,
        APP_LOGO_PATH,
        SCREENSHOT_ICON_PATH,
        OCR_ICON_PATH,
        EXIT_ICON_PATH,
        RESTART_ICON_PATH,
        PREFERENCES_ICON_PATH,
    ):
        if not file.is_file():
            raise FileNotFoundError(f"file '{file}' does not exist.")


self_check()
