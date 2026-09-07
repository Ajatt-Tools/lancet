# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
import dataclasses
import enum
import json
import typing

from beartype.roar import BeartypeCallHintParamViolation
from loguru import logger

from lancet.anki.image_types import AnkiImageFormat
from lancet.actions import LancetAction
from lancet.consts import CFG_PATH, DEFAULT_MODEL_NAME
from lancet.exceptions import ConfigReadError
from lancet.keyboard_shortcuts.listener import to_pynput_shortcuts
from lancet.keyboard_shortcuts.types import (
    QtShortcutStr,
    ShortcutConversionResult,
)


class OcrDestination(enum.Enum):
    """Enum for selecting where OCR results are sent."""

    goldendict = "goldendict"
    clipboard = "clipboard"


def normalize_copy_to(data: dict[str, typing.Any]) -> None:
    """Convert copy_to from a serialized enum name, or drop invalid values to use the default."""
    try:
        copy_to = data["copy_to"]
    except KeyError:
        return
    try:
        data["copy_to"] = OcrDestination[copy_to]
    except (KeyError, TypeError):
        # "invalid", 42 or None → KeyError
        # [] or {} → TypeError
        logger.warning(f"Cannot handle copy_to={copy_to!r} in config. Falling back to default.")
        data.pop("copy_to", None)


def normalize_anki_image_format(data: dict[str, typing.Any]) -> None:
    """Convert an Anki image-format name to an enum, dropping invalid values to use the default."""
    try:
        image_format = data["anki_image_format"]
    except KeyError:
        return
    try:
        data["anki_image_format"] = AnkiImageFormat[image_format]
    except (KeyError, TypeError):
        logger.warning("Cannot handle anki_image_format in config. Falling back to default.")
        data.pop("anki_image_format", None)


@dataclasses.dataclass
class Config:
    """Application configuration with defaults, loaded from and saved to a JSON file."""

    copy_to: OcrDestination = OcrDestination.goldendict
    notification_duration_sec: int = 10
    huggingface_model_name: str = DEFAULT_MODEL_NAME
    huggingface_models: list[str] = dataclasses.field(
        default_factory=lambda: [
            DEFAULT_MODEL_NAME,
            "jzhang533/manga-ocr-base-2025",
        ]
    )
    force_cpu: bool = False
    recover_missed_text: bool = True
    text_detection_resolution: int = 1024
    max_history_size: int = 100
    show_help_bar: bool = True  # Adds hints for keyboard shortcuts, shown at the bottom.

    # Shortcuts
    ocr_shortcut: str = "Alt+O"
    ocr_page_shortcut: str = "Shift+Alt+O"
    screenshot_shortcut: str = ""  # Empty disables the shortcut.
    anki_shortcut: str = "Alt+I"

    # GoldenDict
    path_to_goldendict_executable: str = ""  # Empty enables automatic GoldenDict lookup.

    # Anki
    anki_connect_url: str = "http://127.0.0.1:8765"
    anki_connect_api_key: str = ""
    anki_image_field: str = "Image"
    anki_image_width: int = 0
    anki_image_height: int = 250
    anki_image_quality: int = 33
    anki_image_format: AnkiImageFormat = AnkiImageFormat.webp

    # Screenshot overlay colors (stored as hex ARGB strings, e.g. "#FF0000FF")
    border_thickness: int = 2
    border_color: str = "#7F0000FF"
    fill_color: str = "#3C0080FF"
    outline_color: str = "#7FFF0000"
    fill_brush_color: str = "#557F7F7F"

    # Port used to check if the program is already running.
    bind_port: int = 13129

    @classmethod
    def read_from_file(cls) -> typing.Self:
        """Read the config from the JSON file, returning defaults if the file does not exist."""
        try:
            with open(CFG_PATH, encoding="utf-8") as f:
                data: object = json.load(f)
        except FileNotFoundError:
            logger.info("config file does not exist, falling back to default.")
            return cls()  # Missing config file is not an error.
        except json.JSONDecodeError as ex:
            raise ConfigReadError(f"failed to decode json config file: {ex}") from ex
        except OSError as ex:
            # Permission denied, is a directory, I/O error, etc. Treat as a recoverable read failure.
            raise ConfigReadError(f"failed to open config file: {ex}") from ex
        if not isinstance(data, dict):
            raise ConfigReadError("failed to parse config file: top-level JSON value must be an object")
        normalize_copy_to(data)
        normalize_anki_image_format(data)
        try:
            return cls(**data)
        except (TypeError, BeartypeCallHintParamViolation) as ex:
            raise ConfigReadError(f"failed to parse config file: {ex}") from ex

    @staticmethod
    def file_exists() -> bool:
        """Return True if the config file exists."""
        return CFG_PATH.is_file()

    def save_to_file(self) -> None:
        """Serialize the config to JSON and write it to the config file."""
        data = dataclasses.asdict(self)
        data["copy_to"] = data["copy_to"].name
        data["anki_image_format"] = data["anki_image_format"].name
        CFG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CFG_PATH, "w", encoding="utf-8") as of:
            json.dump(data, of, ensure_ascii=False, indent=4)

    def get_pynput_shortcuts(self) -> ShortcutConversionResult:
        """Return a mapping of key combinations to their shortcut actions."""
        return to_pynput_shortcuts(
            {
                QtShortcutStr(self.ocr_shortcut): LancetAction.ocr,
                QtShortcutStr(self.ocr_page_shortcut): LancetAction.detect_and_ocr,
                QtShortcutStr(self.screenshot_shortcut): LancetAction.screenshot,
                QtShortcutStr(self.anki_shortcut): LancetAction.screenshot_to_anki,
            }
        )


def try_backup_config_file() -> None:
    """Move the invalid config file aside so a fresh default config can be written."""
    try:
        CFG_PATH.replace(CFG_PATH.with_suffix(".old"))  # unconditionally overwrites target
    except OSError as ex:
        logger.error(f"failed to rename invalid config file: {ex}")


class ConfigFileReadResult(typing.NamedTuple):
    """A config file read result, optionally carrying a recoverable error message."""

    cfg: Config
    error: str = ""


def read_config_file() -> ConfigFileReadResult:
    """Read the config file, backing up invalid files and returning defaults on recoverable errors."""
    try:
        return ConfigFileReadResult(Config.read_from_file())
    except ConfigReadError as ex:
        logger.error(str(ex))
        try_backup_config_file()
        return ConfigFileReadResult(Config(), error=str(ex))
