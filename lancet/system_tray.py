# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import concurrent.futures
import datetime
import os
import pathlib
import signal
import sys
import typing
from contextlib import contextmanager

from loguru import logger
from PyQt6.QtGui import QColor, QIcon
from PyQt6.QtWidgets import QApplication, QDialog, QMenu, QSystemTrayIcon, QWidget
from zala.exceptions import ZalaException
from zala.main_window import ScreenshotPreviewOpts, UserSelectionResult
from zala.screenshot import ZalaScreenshot
from zala.take_region import ZalaTakeScreenRegion
from zala.utils import qconnect

from lancet.config import Config
from lancet.consts import (
    APP_LOGO_PATH,
    APP_NAME,
    EXIT_ICON_PATH,
    OCR_ICON_PATH,
    PREFERENCES_ICON_PATH,
    RESTART_ICON_PATH,
    SCREENSHOT_ICON_PATH,
)
from lancet.exceptions import LancetException
from lancet.gui.about_dialog import AboutDialog
from lancet.gui.geom_dialog import SaveAndRestoreGeomDialog
from lancet.gui.preferences import PreferencesDialog, SettingsApplyResult
from lancet.keyboard_shortcuts.listener import LancetShortcutManager
from lancet.keyboard_shortcuts.types import LancetShortcutEnum, PyShortcutStr
from lancet.model_utils.model_loader import BackgroundModelLoader
from lancet.model_utils.ocr_service import OcrService
from lancet.model_utils.ocr_workflow import OcrWorkflow, ensure_cursor_restored
from lancet.notifications import NotifySend
from lancet.ocr_history import OcrHistory


def filename_compatible_datetime() -> str:
    """Generate a timestamped file name compatible with the current system."""
    return datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def make_output_file_path() -> pathlib.Path:
    """Generate a timestamped file path under ~/Pictures/Screenshots for saving a screenshot."""
    return pathlib.Path.home() / "Pictures" / "Screenshots" / f"{APP_NAME}_{filename_compatible_datetime()}.png"


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
        show_help=cfg.show_help_bar,
    )


class OpenDialogs:
    _name_to_instance: dict[str, QDialog]

    def __init__(self):
        self._name_to_instance = {}

    def is_locked(self) -> bool:
        return len(self._name_to_instance) > 0

    def _disown_if_present(self, name: str) -> None:
        self._name_to_instance.pop(name, None)

    @contextmanager
    def lock[D: SaveAndRestoreGeomDialog](self, dialog: D) -> typing.Generator[D]:
        if dialog.name in self._name_to_instance:
            raise LancetException("already locked")

        self._name_to_instance[dialog.name] = dialog
        # dialog's result code is passed to the slot.
        # https://doc.qt.io/qt-6/qdialog.html#finished
        qconnect(dialog.finished, lambda code: self._disown_if_present(dialog.name))

        try:
            yield dialog
        finally:
            self._disown_if_present(dialog.name)


class LancetSystemTray(QSystemTrayIcon):
    """
    System tray application containing all global actions
    """

    _loader: BackgroundModelLoader
    _ocr_workflow: OcrWorkflow
    _app: QApplication
    _take: ZalaTakeScreenRegion
    _cfg: Config
    _open_dialogs: OpenDialogs
    _hotkeys: LancetShortcutManager

    def __init__(self, app: QApplication, cfg: Config, parent: QWidget | None = None) -> None:
        """Set up the system tray icon, context menu, OCR model, and keyboard shortcuts."""
        super().__init__(parent)
        self.setIcon(QIcon(str(APP_LOGO_PATH)))

        # Setup members
        self._open_dialogs = OpenDialogs()
        self._executor = concurrent.futures.ThreadPoolExecutor()
        self._app = app
        self._cfg = cfg
        self._notify = NotifySend(self, duration_sec=self._cfg.notification_duration_sec)
        self._take = ZalaTakeScreenRegion(scr=ZalaScreenshot(app))
        self._history = OcrHistory(self._cfg.max_history_size)
        self._loader = BackgroundModelLoader.new(
            cfg=self._cfg,
            notify=self._notify,
            executor=self._executor,
        )
        self._ocr_workflow = OcrWorkflow(
            app=self._app,
            cfg=self._cfg,
            loader=self._loader,
            ocr_service=OcrService(loader=self._loader, cfg=self._cfg),
            notify=self._notify,
            history=self._history,
            executor=self._executor,
        )
        self._hotkeys = LancetShortcutManager(self._build_shortcuts())

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
        menu.addAction(
            QIcon(str(OCR_ICON_PATH)),
            format_hotkey("Detect and OCR", self._cfg.ocr_page_shortcut),
            self.detect_and_make_ocr_screenshot,
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

        # Init models in background
        self._loader.load_all()
        signal.signal(signal.SIGINT, self._sigint_handler)

        # Set keyboard shortcuts
        self._hotkeys.start_listener()
        qconnect(self._hotkeys.signals.shortcut_activated, self.process_keyboard_shortcut)

    def _build_shortcuts(self) -> dict[PyShortcutStr, LancetShortcutEnum]:
        """Parse keyboard shortcuts from config, log failures, and return valid hotkeys."""
        result = self._cfg.get_pynput_shortcuts()
        if error_message := result.format_failures():
            logger.error(error_message)
            self._notify.notify(error_message)
        return result.hotkeys

    def process_keyboard_shortcut(self, shortcut: LancetShortcutEnum) -> None:
        """Dispatch a keyboard shortcut event to the corresponding action."""
        if self._open_dialogs.is_locked():
            logger.info(f"Shortcut pressed while dialog open: {shortcut.name}")
            return
        match shortcut:
            case LancetShortcutEnum.ocr_shortcut:
                self.make_ocr_screenshot()
            case LancetShortcutEnum.ocr_page_shortcut:
                self.detect_and_make_ocr_screenshot()
            case LancetShortcutEnum.screenshot_shortcut:
                self.make_screenshot_area()

    def open_about(self) -> None:
        """Open the About dialog."""
        with self._open_dialogs.lock(AboutDialog()) as dialog:
            dialog.exec()

    def open_preferences(self) -> None:
        """Open the preferences dialog and reload shortcuts if settings are applied."""
        with self._open_dialogs.lock(PreferencesDialog(self._cfg, self._history)) as dialog:
            qconnect(dialog.settings_applied, self._on_settings_changed)
            qconnect(dialog.history_list.copy_requested, self._ocr_workflow.copy_ocr_result)
            dialog.exec()

    def _on_settings_changed(self, settings_applied: SettingsApplyResult) -> None:
        """Handle the result of applying settings, reloading all affected components on success."""
        if settings_applied.success:
            self._hotkeys.restart_listener(self._build_shortcuts())
            self._notify.set_duration(self._cfg.notification_duration_sec)
            self._history.set_entries(settings_applied.ocr_history, max_size=self._cfg.max_history_size)
            self._loader.on_config_changed()
        else:
            self._notify.notify(f"failed to apply config: {settings_applied.error}")

    def restart(self) -> None:
        """Restart the application by replacing the current process with a fresh instance."""
        # https://docs.python.org/3.14/library/os.html#os.execv
        self.quit()
        os.execv(sys.executable, [sys.executable, *sys.argv])

    def _sigint_handler(self, _signum: int, _frame: typing.Any) -> None:
        """Handle SIGINT by quitting the application gracefully."""
        self.quit()

    def quit(self) -> None:
        """Stop hotkeys and quit the application."""
        logger.info("Quit Lancet.")
        self._hotkeys.stop_listener()
        self._executor.shutdown(wait=True)
        self._app.quit()

    def make_screenshot_area(self) -> None:
        """Open the full-screen selection overlay for taking an area screenshot."""
        try:
            self._take.select_area(on_finish=self.process_select_result, opts=make_preview_opts(self._cfg))
        except ZalaException as ex:
            logger.error(str(ex))
            self._notify.notify(str(ex))

    def make_ocr_screenshot(self) -> None:
        """Open the full-screen selection overlay for OCR recognition of the selected area."""
        try:
            self._take.select_area(on_finish=self._ocr_workflow.run_ocr, opts=make_preview_opts(self._cfg))
        except ZalaException as ex:
            logger.error(str(ex))
            self._notify.notify(str(ex))

    def detect_and_make_ocr_screenshot(self) -> None:
        """Open the full-screen selection overlay for speech bubble detection and OCR."""
        try:
            self._take.select_area(
                on_finish=self._ocr_workflow.run_speech_bubble_ocr,
                opts=make_preview_opts(self._cfg),
            )
        except ZalaException as ex:
            logger.error(str(ex))
            self._notify.notify(str(ex))

    def process_select_result(self, user_selection: UserSelectionResult) -> None:
        """Save the user's screenshot selection to a file."""
        ensure_cursor_restored()
        if not user_selection.pixmap:
            self._notify.notify("Selection aborted")
            return
        output_path = make_output_file_path()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if user_selection.pixmap.save(str(output_path)):
            self._notify.notify(f"Selection saved to {output_path}")
        else:
            self._notify.notify(f"Failed to save selection to {output_path}")
