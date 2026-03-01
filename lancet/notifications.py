# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from PyQt6.QtWidgets import QSystemTrayIcon

from lancet.consts import APP_NAME
from lancet.find_executable import find_executable, run_and_disown


class NotifySend:
    def __init__(self, tray: QSystemTrayIcon, duration_sec: int = 10) -> None:
        self._notify_send = find_executable("notify-send")
        self._tray = tray
        self._duration_sec = duration_sec

    def notify(self, msg: str) -> None:
        if self._notify_send:
            # --expire-time=TIME: The duration, in milliseconds.
            run_and_disown([self._notify_send, APP_NAME, msg, "--expire-time", f"{self._duration_sec * 1_000}"])
        else:
            self._tray.showMessage(APP_NAME, msg)
