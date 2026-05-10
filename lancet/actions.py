# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
import enum


class LancetAction(enum.Enum):
    """
    Actions available via the IPC command channel.

    Names double as the JSON "action" field in IPC requests.
    Used by CLI commands to tell the running daemon what to do.
    """

    # TODO merge with LancetShortcutEnum
    ocr = "ocr"
    detect_and_ocr = "detect_and_ocr"
    screenshot = "screenshot"


class LancetShortcutEnum(enum.Enum):
    """
    Enum identifying the all actions Lancet can perform and all available keyboard shortcut actions.

    Used both by the keyboard-shortcut dispatcher and the IPC command channel,
    so that CLI commands and hotkeys share one authoritative action vocabulary.
    String values double as the JSON "action" field in IPC requests.
    """

    ocr_shortcut = enum.auto()
    ocr_page_shortcut = enum.auto()
    screenshot_shortcut = enum.auto()
