# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
import dataclasses
import enum
import json
from typing import Self

from lancet.consts import CFG_PATH
from lancet.ocr.manga_ocr_base import ConfigReadError


class OcrDestination(enum.Enum):
    goldendict = "goldendict"
    clipboard = "clipboard"


@dataclasses.dataclass
class Config:
    copy_to: OcrDestination = OcrDestination.goldendict
    notification_duration_sec: int = 10
    huggingface_model_name: str = "tatsumoto/manga-ocr-base"
    huggingface_models: list[str] = dataclasses.field(
        default_factory=lambda: [
            "tatsumoto/manga-ocr-base",
            "jzhang533/manga-ocr-base-2025",
        ]
    )
    force_cpu: bool = False
    ocr_shortcut: str = "Alt+O"
    screenshot_shortcut: str = ""  # unset

    @classmethod
    def read_from_file(cls) -> Self:
        try:
            with open(CFG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            return cls()
        if "copy_to" in data:
            data["copy_to"] = OcrDestination[data["copy_to"]]
        try:
            return cls(**data)
        except TypeError as ex:
            raise ConfigReadError(f"failed to parse config file: {ex}") from ex

    def save_to_file(self) -> None:
        data = dataclasses.asdict(self)
        data["copy_to"] = data["copy_to"].name
        CFG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CFG_PATH, "w", encoding="utf-8") as of:
            json.dump(data, of, ensure_ascii=False, indent=4)
