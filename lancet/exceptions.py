# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html


class LancetException(Exception):
    pass


class ConfigReadError(LancetException, RuntimeError):
    """Raised when the configuration file cannot be read or parsed."""

    pass


class PortAlreadyInUseError(LancetException, OSError):
    pass


class PixmapConversionError(LancetException, ValueError):
    pass


class LancetHTTPError(LancetException, OSError):
    pass


class KeyboardShortcutParseError(LancetException, ValueError):
    """Raised when a keyboard shortcut string cannot be converted to pynput format."""

    pass


class DuplicateShortcutError(KeyboardShortcutParseError):
    """Raised when two registered shortcuts resolve to the same set of keys."""

    pass
