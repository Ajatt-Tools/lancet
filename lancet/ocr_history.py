# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import collections
import json
from collections.abc import Sequence

from lancet.config import Config
from lancet.consts import HISTORY_FILE_PATH


def _load_history() -> list[str]:
    """Read the history entries from the JSON file."""
    try:
        with open(HISTORY_FILE_PATH, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return [str(entry) for entry in data]
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return []


class OcrHistory:
    """Stores and retrieves a list of previous OCR results, persisted to a JSON file."""

    def __init__(self, cfg: Config) -> None:
        """Load the history from disk, or start with an empty list if the file does not exist."""
        self._cfg = cfg
        self._entries: collections.deque[str] = collections.deque(_load_history(), maxlen=cfg.max_history_size)

    def _save_history(self) -> None:
        """Write the current history entries to the JSON file."""
        HISTORY_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(HISTORY_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(tuple(self._entries), f, ensure_ascii=False, indent=2)

    def add_to_history(self, text: str) -> None:
        """Add a new OCR result to the beginning of the history and save."""
        text = text.strip()
        if not text:
            return

        self._entries.appendleft(text)
        self._save_history()

    def entries(self) -> Sequence[str]:
        """Return all history entries, newest first."""
        return self._entries

    def set_entries(self, entries: list[str]) -> None:
        self._entries.clear()
        self._entries.extend(entries)
        self._save_history()

    def clear(self) -> None:
        """Remove all history entries and save."""
        self._entries.clear()
        self._save_history()

    def remove(self, indices: Sequence[int]) -> None:
        """Remove entries at the given indices and save."""
        for idx in sorted(indices, reverse=True):
            if 0 <= idx < len(self._entries):
                del self._entries[idx]
        self._save_history()
