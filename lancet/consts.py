# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
import os
import pathlib

APP_NAME = "Lancet"
THIS_DIR = pathlib.Path(__file__).resolve().parent
ICONS_DIR = THIS_DIR / "icons"
APP_LOGO_PATH = ICONS_DIR / "logo.ico"
SCREENSHOT_ICON_PATH = ICONS_DIR / "screenshot.png"
OCR_ICON_PATH = ICONS_DIR / "ocr.png"
EXIT_ICON_PATH = ICONS_DIR / "exit.png"
RESTART_ICON_PATH = ICONS_DIR / "restart.png"
PREFERENCES_ICON_PATH = ICONS_DIR / "preferences.png"
CFG_DIR_PATH = pathlib.Path(os.environ.get("XDG_CONFIG_HOME", pathlib.Path.home() / ".config")) / APP_NAME.lower()
CFG_PATH = CFG_DIR_PATH / f"{APP_NAME.lower()}.json"
