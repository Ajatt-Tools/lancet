# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import datetime
import os
import pathlib
import signal
import sys

from PyQt6.QtCore import QThreadPool
from PyQt6.QtGui import QColor, QIcon
from PyQt6.QtWidgets import QSystemTrayIcon, QApplication, QMenu, QWidget
from loguru import logger
from zala.main_window import ZalaSelect, UserSelectionResult, ScreenshotPreviewOpts
from zala.screenshot import ZalaScreenshot

from lancet.config import Config, OcrDestination
from lancet.consts import (
    APP_LOGO_PATH,
    SCREENSHOT_ICON_PATH,
    EXIT_ICON_PATH,
    OCR_ICON_PATH,
    RESTART_ICON_PATH,
    PREFERENCES_ICON_PATH,
)
from lancet.find_executable import run_and_disown, find_executable
from lancet.gui.about_dialog import AboutDialog
from lancet.keyboard_shortcuts import LancetShortcutManager, LancetShortcutEnum, KeyboardShortcut
from lancet.notifications import NotifySend
from lancet.ocr.manga_ocr_launcher import MangaOCRLauncher, run_ocr
from lancet.ocr.op import QThreadPoolOp
from lancet.ocr_history import OcrHistory
from lancet.preferences import PreferencesDialog, SettingsApplyResult


def make_output_file_path() -> pathlib.Path:
    """Generate a timestamped file path under ~/Pictures/Screenshots for saving a screenshot."""
    return pathlib.Path.home() / "Pictures" / "Screenshots" / f"{datetime.datetime.now().isoformat()}.png"


def format_hotkey(menu_label: str, keyboard_shortcut: str) -> str:
    """Append the keyboard shortcut in parentheses to the menu label, if one is set."""
    if keyboard_shortcut:
        return f"{menu_label} ({keyboard_shortcut})"
    return menu_label


def make_preview_opts(cfg: Config) -> ScreenshotPreviewOpts:
    """Build screenshot overlay options from the current config."""
    return ScreenshotPreviewOpts(
        border_thickness=cfg.border_thickness,
        border_color=QColor.fromString(cfg.border_color),
        fill_color=QColor.fromString(cfg.fill_color),
        outline_color=QColor.fromString(cfg.outline_color),
        fill_brush_color=QColor.fromString(cfg.fill_brush_color),
    )


class LancetSystemTray(QSystemTrayIcon):
    """
    System tray application containing all global actions
    """

    _ocr: MangaOCRLauncher
    _scr: ZalaScreenshot
    _app: QApplication
    _sel: ZalaSelect | None = None
    _cfg: Config
    _hotkeys: LancetShortcutManager | None = None

    def __init__(self, app: QApplication, parent: QWidget | None = None) -> None:
        """Set up the system tray icon, context menu, OCR model, and keyboard shortcuts."""
        super().__init__(parent)
        self._app = app
        self._scr = ZalaScreenshot(app)

        # State trackers and configurations
        self.threadpool = QThreadPool.globalInstance()
        self._cfg = Config.read_from_file()
        self._notify = NotifySend(self, duration_sec=self._cfg.notification_duration_sec)
        self._history = OcrHistory(self._cfg.max_history_size)
        self._ocr = MangaOCRLauncher(
            parent=self,
            notify=self._notify,
            threadpool=self.threadpool,
            pretrained_model_name_or_path=self._cfg.huggingface_model_name,
            force_cpu=self._cfg.force_cpu,
        )
        self.setIcon(QIcon(str(APP_LOGO_PATH)))
        # Menu
        menu = QMenu(parent)
        self.setContextMenu(menu)

        # Menu Actions
        menu.addAction(
            QIcon(str(SCREENSHOT_ICON_PATH)),
            format_hotkey("Screenshot area", self._cfg.screenshot_shortcut),
            self.make_screenshot_area,
        )
        menu.addAction(
            QIcon(str(OCR_ICON_PATH)),
            format_hotkey("OCR screenshot", self._cfg.ocr_shortcut),
            self.make_ocr_screenshot,
        )
        menu.addSeparator()
        menu.addAction(QIcon(str(PREFERENCES_ICON_PATH)), "Preferences…", self.open_preferences)
        menu.addAction(QIcon(str(RESTART_ICON_PATH)), "Restart", self.restart)
        menu.addAction(QIcon(str(APP_LOGO_PATH)), "About…", self.open_about)
        menu.addAction(
            QIcon(str(EXIT_ICON_PATH)),
            "Exit",
            self.quit,
        )

        # Init model in background
        self._ocr.init_manga_ocr()
        signal.signal(signal.SIGINT, self.quit)

        # Set keyboard shortcuts
        self._load_keyboard_shortcuts()

    def _load_keyboard_shortcuts(self) -> None:
        """Stop any existing hotkey listener and start a new one from the current config."""
        self._stop_hotkeys()

        try:
            self._hotkeys = LancetShortcutManager(self.get_keyboard_shortcuts())
        except Exception as e:
            self._notify.notify(f"failed to load keyboard shortcuts: {e}")
        else:
            self._hotkeys.start()
            self._hotkeys.signals.shortcut_activated.connect(self.process_keyboard_shortcut)

    def get_keyboard_shortcuts(self) -> dict[LancetShortcutEnum, KeyboardShortcut]:
        """Return a mapping of shortcut actions to their key combinations, excluding empty ones."""
        hotkey_dict = {
            LancetShortcutEnum.ocr_shortcut: self._cfg.ocr_shortcut,
            LancetShortcutEnum.screenshot_shortcut: self._cfg.screenshot_shortcut,
        }
        hotkey_dict = {k: v.strip() for k, v in hotkey_dict.items()}
        return {k: v for k, v in hotkey_dict.items() if v}

    def process_keyboard_shortcut(self, shortcut: LancetShortcutEnum) -> None:
        """Dispatch a keyboard shortcut event to the corresponding action."""
        match shortcut:
            case LancetShortcutEnum.ocr_shortcut:
                self.make_ocr_screenshot()
            case LancetShortcutEnum.screenshot_shortcut:
                self.make_screenshot_area()

    def open_about(self) -> None:
        """Open the About dialog."""
        dialog = AboutDialog()
        dialog.exec()

    def open_preferences(self) -> None:
        """Open the preferences dialog and reload shortcuts if settings are applied."""
        dialog = PreferencesDialog(self._cfg, self._history)
        dialog.settings_applied.connect(self._on_settings_changed)
        dialog.history_list.copy_requested.connect(self.copy_ocr_result)
        dialog.exec()

    def _on_settings_changed(self, settings_applied: SettingsApplyResult) -> None:
        """Handle the result of applying settings, reloading all affected components on success."""
        if settings_applied.success:
            self._load_keyboard_shortcuts()
            self._notify.set_duration(self._cfg.notification_duration_sec)
            self._history.set_entries(settings_applied.ocr_history, max_size=self._cfg.max_history_size)
            self._ocr.load_new_config(self._cfg.huggingface_model_name, self._cfg.force_cpu)
        else:
            self._notify.notify(f"failed to apply config: {settings_applied.error}")

    def _stop_hotkeys(self) -> None:
        """Stop and discard the current hotkey listener if one is active."""
        if self._hotkeys:
            self._hotkeys.stop()
            self._hotkeys = None

    def restart(self) -> None:
        """Restart the application by replacing the current process with a fresh instance."""
        # https://docs.python.org/3.14/library/os.html#os.execv
        logger.info("Restarting Lancet.")
        self._stop_hotkeys()
        self._app.quit()
        os.execv(sys.executable, [sys.executable, *sys.argv])

    def quit(self) -> None:
        """Stop hotkeys and quit the application."""
        logger.info("Quit Lancet.")
        self._stop_hotkeys()
        self._app.quit()

    def make_screenshot_area(self) -> None:
        """Open the full-screen selection overlay for taking an area screenshot."""
        self._sel = ZalaSelect(self._scr.capture_screen(), opts=make_preview_opts(self._cfg))
        self._sel.selection_finished.connect(self.process_select_result)
        self._sel.showFullScreen()

    def make_ocr_screenshot(self) -> None:
        """Open the full-screen selection overlay for OCR recognition of the selected area."""
        self._sel = ZalaSelect(self._scr.capture_screen(), opts=make_preview_opts(self._cfg))
        self._sel.selection_finished.connect(self.process_ocr_result)
        self._sel.showFullScreen()

    def process_select_result(self, user_selection: UserSelectionResult) -> None:
        """Save the user's screenshot selection to a file."""
        if not user_selection.pixmap:
            self._notify.notify("Selection aborted")
            return
        output_path = make_output_file_path()
        output_path.mkdir(parents=True, exist_ok=True)
        if user_selection.pixmap.save(str(output_path)):
            self._notify.notify(f"Selection saved to {output_path}")
        else:
            self._notify.notify(f"Failed to save selection to {output_path}")

    def process_ocr_result(self, user_selection: UserSelectionResult) -> None:
        """Run OCR on the user's selection in a background thread and handle the result."""
        if not user_selection.pixmap:
            self._notify.notify(user_selection.error.capitalize())
            return

        if not (status := self._ocr.is_ready()).is_ready:
            self._notify.notify(status.what())
            return

        def on_ocr_finished(text: str) -> None:
            if text:
                self._history.add_to_history(text)
                self.copy_ocr_result(text)
            else:
                self._notify.notify("OCR returned no text")

        def on_failed(e: Exception) -> None:
            logger.error(f"failed to recognize image: {e}")
            self._notify.notify(f"failed to recognize image: {e}")

        (
            QThreadPoolOp(parent=self, op=lambda: run_ocr(user_selection.pixmap, self._ocr), threadpool=self.threadpool)
            .success(on_ocr_finished)
            .failure(on_failed)
            .run_in_background()
        )

    def copy_ocr_result(self, text: str) -> None:
        """Send the OCR result to the configured destination (clipboard or GoldenDict)."""
        match self._cfg.copy_to:
            case OcrDestination.goldendict:
                run_and_disown([find_executable("goldendict") or "goldendict", text])
            case OcrDestination.clipboard:
                self._app.clipboard().setText(text)
        self._notify.notify(f"OCR result copied: {text}")
