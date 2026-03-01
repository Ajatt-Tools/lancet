# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
import os
import pathlib
import sys

APP_NAME = "Lancet"
THIS_DIR = pathlib.Path(__file__).resolve().parent
DESKTOP_FILE = THIS_DIR / f"{APP_NAME.lower()}.desktop"
ICONS_DIR = THIS_DIR / "icons"
APP_LOGO_PATH = ICONS_DIR / "logo.png"
SCREENSHOT_ICON_PATH = ICONS_DIR / "screenshot.png"
OCR_ICON_PATH = ICONS_DIR / "ocr.png"
EXIT_ICON_PATH = ICONS_DIR / "exit.png"
RESTART_ICON_PATH = ICONS_DIR / "restart.png"
PREFERENCES_ICON_PATH = ICONS_DIR / "preferences.png"
CFG_DIR_PATH = pathlib.Path(os.environ.get("XDG_CONFIG_HOME", pathlib.Path.home() / ".config")) / APP_NAME.lower()
CFG_PATH = CFG_DIR_PATH / f"{APP_NAME.lower()}.json"

CACHE_DIR_PATH = pathlib.Path(os.environ.get("XDG_CACHE_HOME", pathlib.Path.home() / ".cache")) / APP_NAME.lower()
HISTORY_FILE_PATH = CACHE_DIR_PATH / "ocr_history.json"
GEOMETRY_FILE_PATH = CACHE_DIR_PATH / "geometry"

IS_MAC = sys.platform.startswith("darwin")
IS_WIN = sys.platform.startswith("win32")
