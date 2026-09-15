# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
import dataclasses
import enum
import json
import os
import pathlib
import tempfile
import typing
from collections.abc import Mapping
from contextlib import AbstractContextManager

from beartype.roar import BeartypeCallHintParamViolation
from loguru import logger
from PyQt6.QtGui import QColor
from zala.config import ScreenshotPreviewOpts
from zala.utils import clamp

from lancet.actions import LancetAction
from lancet.anki.image_types import AnkiImageFormat
from lancet.consts import (
    ANKI_FIELD_SEPARATOR,
    ANKI_IMAGE_MAX_DIMENSION,
    ANKI_IMAGE_MAX_QUALITY,
    CFG_PATH,
    CONFIG_FILE_MODE,
    DEFAULT_ANKICONNECT_URL,
    DEFAULT_MODEL_NAME,
)
from lancet.exceptions import ConfigReadError
from lancet.keyboard_shortcuts.listener import to_pynput_shortcuts
from lancet.keyboard_shortcuts.types import (
    QtShortcutStr,
    ShortcutConversionResult,
)

type CfgValueTypes = bool | str | int | float | enum.Enum


class OcrDestination(enum.Enum):
    """Enum for selecting where OCR results are sent."""

    goldendict = "goldendict"
    clipboard = "clipboard"


def normalize_enum[T: enum.Enum](data: dict[str, typing.Any], *, key: str, enum_type: type[T]) -> None:
    """Convert one serialized enum name or remove an invalid value."""
    try:
        value = data[key]
    except KeyError:
        return
    try:
        data[key] = enum_type[value]
    except (KeyError, TypeError):
        # "invalid", 42 or None → KeyError
        # [] or {} → TypeError
        logger.warning(f"Cannot handle {key}={value!r} in config. Falling back to default.")
        data.pop(key, None)


def read_config_dict() -> dict[str, typing.Any]:
    """Decode the config file and validate that its root is a JSON object."""
    try:
        with open(CFG_PATH, encoding="utf-8") as f:
            data: object = json.load(f)
    except FileNotFoundError:
        logger.info("config file does not exist, falling back to default.")
        return {}  # Missing config file is not an error.
    except json.JSONDecodeError as ex:
        raise ConfigReadError(f"failed to decode json config file: {ex}") from ex
    except OSError as ex:
        # Permission denied, is a directory, I/O error, etc. Treat as a recoverable read failure.
        raise ConfigReadError(f"failed to open config file: {ex}") from ex
    if not isinstance(data, dict):
        raise ConfigReadError("failed to parse config file: top-level JSON value must be an object")
    return data


def make_temp_config_file() -> AbstractContextManager[typing.IO[str]]:
    """Create an open text temporary file for atomic config replacement."""
    return tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        prefix=f".{CFG_PATH.name}.",
        suffix=".tmp",
        dir=CFG_PATH.parent,
        delete=False,
    )


def write_config_dict(data: Mapping[str, object]) -> None:
    """Atomically write config through an owner-only sibling temporary file."""
    CFG_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path: pathlib.Path | None = None
    try:
        with make_temp_config_file() as output:
            temp_path: pathlib.Path = pathlib.Path(output.name)
            temp_path.chmod(CONFIG_FILE_MODE)
            json.dump(data, output, ensure_ascii=False, indent=4)
            output.flush()
            os.fsync(output.fileno())
        assert temp_path is not None
        temp_path.replace(CFG_PATH)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


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
    anki_connect_url: str = DEFAULT_ANKICONNECT_URL
    anki_connect_api_key: str = ""
    anki_image_field: str = "Image"
    anki_field_separator: str = ANKI_FIELD_SEPARATOR
    anki_image_width: int = 0
    anki_image_height: int = 250
    anki_image_quality: int = 33
    anki_image_format: AnkiImageFormat = AnkiImageFormat.avif

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
        data = read_config_dict()
        normalize_enum(data, key="copy_to", enum_type=OcrDestination)
        normalize_enum(data, key="anki_image_format", enum_type=AnkiImageFormat)
        try:
            self = cls(**data)
        except (TypeError, BeartypeCallHintParamViolation) as ex:
            raise ConfigReadError(f"failed to parse config file: {ex}") from ex
        self.normalize_anki_settings()
        return self

    def normalize_anki_settings(self) -> None:
        """Trim Anki target text and clamp image dimensions and quality to supported ranges."""
        self.anki_connect_url = self.anki_connect_url.strip()
        self.anki_image_field = self.anki_image_field.strip()
        self.anki_image_width = clamp(0, self.anki_image_width, ANKI_IMAGE_MAX_DIMENSION)
        self.anki_image_height = clamp(0, self.anki_image_height, ANKI_IMAGE_MAX_DIMENSION)
        self.anki_image_quality = clamp(0, self.anki_image_quality, ANKI_IMAGE_MAX_QUALITY)

    @staticmethod
    def file_exists() -> bool:
        """Return True if the config file exists."""
        return CFG_PATH.is_file()

    def save_to_file(self) -> None:
        """Normalize and serialize the config to JSON."""
        self.normalize_anki_settings()
        data = dataclasses.asdict(self)
        data["copy_to"] = data["copy_to"].name
        data["anki_image_format"] = data["anki_image_format"].name
        write_config_dict(data)

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
