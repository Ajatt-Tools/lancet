# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
import os
import pathlib
import sys

type P = pathlib.Path
type S = str
type B = bool
type Int = int

APP_NAME: S = "Lancet"
THIS_DIR: P = pathlib.Path(__file__).resolve().parent
DESKTOP_FILE: P = THIS_DIR / f"{APP_NAME.lower()}.desktop"
ICONS_DIR: P = THIS_DIR / "icons"
APP_LOGO_PATH: P = ICONS_DIR / "app_logo.png"
SCREENSHOT_ICON_PATH: P = ICONS_DIR / "screenshot.png"
ANKI_SCREENSHOT_ICON_PATH: P = ICONS_DIR / "screenshot_to_anki.svg"
OCR_ICON_PATH: P = ICONS_DIR / "ocr.svg"
DETECT_AND_OCR_ICON_PATH: P = ICONS_DIR / "detect_and_ocr.svg"
EXIT_ICON_PATH: P = ICONS_DIR / "exit.png"
RESTART_ICON_PATH: P = ICONS_DIR / "restart.png"
PREFERENCES_ICON_PATH: P = ICONS_DIR / "preferences.png"
XDG_CONFIG_HOME: P = pathlib.Path(os.environ.get("XDG_CONFIG_HOME", pathlib.Path.home() / ".config"))
CFG_DIR_PATH: P = XDG_CONFIG_HOME / APP_NAME.lower()
CFG_PATH: P = CFG_DIR_PATH / f"{APP_NAME.lower()}.json"

CACHE_DIR_PATH: P = pathlib.Path(os.environ.get("XDG_CACHE_HOME", pathlib.Path.home() / ".cache")) / APP_NAME.lower()
HISTORY_FILE_PATH: P = CACHE_DIR_PATH / "ocr_history.json"
GEOMETRY_FILE_PATH: P = CACHE_DIR_PATH / "geometry"

# Default pane widths (px) for the preferences dialog splitter: settings on the left, OCR history on the right.
PREFERENCES_SPLITTER_SETTINGS_WIDTH: Int = 400
PREFERENCES_SPLITTER_HISTORY_WIDTH: Int = 300
ANKI_IMAGE_MAX_DIMENSION: Int = 4096
ANKI_IMAGE_MAX_QUALITY: Int = 100

IS_MAC: B = sys.platform.startswith("darwin")
IS_WIN: B = sys.platform.startswith("win32")

GITHUB_URL: S = "https://github.com/Ajatt-Tools/lancet"
CHAT_URL: S = "https://ajatt.top/blog/join-our-community.html"

DEFAULT_MODEL_NAME: S = "tatsumoto/manga-ocr-base"
OCR_JOIN_STR: S = " "
DEFAULT_ANKICONNECT_URL: S = "http://127.0.0.1:8765"
ANKI_FIELD_SEPARATOR: S = "<br>"


def self_check() -> None:
    """Raise FileNotFoundError when a packaged application resource is missing."""
    for file in (
        DESKTOP_FILE,
        APP_LOGO_PATH,
        SCREENSHOT_ICON_PATH,
        ANKI_SCREENSHOT_ICON_PATH,
        OCR_ICON_PATH,
        DETECT_AND_OCR_ICON_PATH,
        EXIT_ICON_PATH,
        RESTART_ICON_PATH,
        PREFERENCES_ICON_PATH,
    ):
        if not file.is_file():
            raise FileNotFoundError(f"file '{file}' does not exist.")


self_check()
