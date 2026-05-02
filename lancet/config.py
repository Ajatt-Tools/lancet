# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
import dataclasses
import enum
import json
from typing import Any, Self

from loguru import logger

from lancet.consts import CFG_PATH, DEFAULT_MODEL_NAME
from lancet.exceptions import ConfigReadError
from lancet.keyboard_shortcuts.listener import to_pynput_shortcuts
from lancet.keyboard_shortcuts.types import (
    LancetShortcutEnum,
    QtShortcutStr,
    ShortcutConversionResult,
)


class OcrDestination(enum.Enum):
    """Enum for selecting where OCR results are sent."""

    goldendict = "goldendict"
    clipboard = "clipboard"


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
    screenshot_shortcut: str = ""  # unset

    # Screenshot overlay colors (stored as hex ARGB strings, e.g. "#FF0000FF")
    border_thickness: int = 2
    border_color: str = "#7F0000FF"
    fill_color: str = "#3C0080FF"
    outline_color: str = "#7FFF0000"
    fill_brush_color: str = "#557F7F7F"

    # Port used to check if the program is already running.
    bind_port: int = 13129

    @classmethod
    def read_from_file(cls) -> Self:
        """Read the config from the JSON file, returning defaults if the file does not exist."""
        try:
            with open(CFG_PATH, encoding="utf-8") as f:
                data: dict[str, Any] = json.load(f)
        except FileNotFoundError:
            logger.warning("config file does not exist, falling back to default.")
            return cls()
        except json.JSONDecodeError as ex:
            raise ConfigReadError(f"failed to decode json config file: {ex}") from ex
        try:
            data["copy_to"] = OcrDestination[data["copy_to"]]
        except KeyError:
            logger.warning(
                f"Unknown copy_to value {data.get('copy_to', 'missing')!r} in config, falling back to default."
            )
            data.pop("copy_to", None)
        try:
            return cls(**data)
        except TypeError as ex:
            raise ConfigReadError(f"failed to parse config file: {ex}") from ex

    @staticmethod
    def file_exists() -> bool:
        return CFG_PATH.is_file()

    def save_to_file(self) -> None:
        """Serialize the config to JSON and write it to the config file."""
        data = dataclasses.asdict(self)
        data["copy_to"] = data["copy_to"].name
        CFG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CFG_PATH, "w", encoding="utf-8") as of:
            json.dump(data, of, ensure_ascii=False, indent=4)

    def get_pynput_shortcuts(self) -> ShortcutConversionResult:
        """Return a mapping of key combinations to their shortcut actions."""
        return to_pynput_shortcuts(
            {
                QtShortcutStr(self.ocr_shortcut): LancetShortcutEnum.ocr_shortcut,
                QtShortcutStr(self.ocr_page_shortcut): LancetShortcutEnum.ocr_page_shortcut,
                QtShortcutStr(self.screenshot_shortcut): LancetShortcutEnum.screenshot_shortcut,
            }
        )
