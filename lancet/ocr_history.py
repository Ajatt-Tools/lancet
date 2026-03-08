# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import collections
import itertools
import json
from collections.abc import Sequence
from typing import Self

from lancet.consts import HISTORY_FILE_PATH


def _load_history() -> Sequence[str]:
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

    def __init__(self, max_history_size: int = 10) -> None:
        """Load the history from disk, or start with an empty list if the file does not exist."""
        self._entries: collections.deque[str] = collections.deque(_load_history(), maxlen=max_history_size)

    def _save_history(self) -> Self:
        """Write the current history entries to the JSON file."""
        HISTORY_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(HISTORY_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(tuple(self._entries), f, ensure_ascii=False, indent=2)
        return self

    def add_to_history(self, text: str) -> Self:
        """Add a new OCR result to the beginning of the history and save."""
        if text := text.strip():
            self._entries.appendleft(text)
            self._save_history()
        return self

    def entries(self) -> Sequence[str]:
        """Return all history entries, newest first."""
        return self._entries

    def set_max_size(self, max_size: int) -> Self:
        """Update the maximum history size, trimming old entries if needed."""
        self._entries = collections.deque(self._entries, maxlen=max(1, max_size))
        self._save_history()
        return self

    def set_entries(self, entries: Sequence[str], max_size: int = 0) -> Self:
        """Replace all history entries and save."""
        max_size = max(1, max_size or self._entries.maxlen)
        self._entries = collections.deque(itertools.islice(entries, max_size), maxlen=max_size)
        self._save_history()
        return self

    def clear(self) -> Self:
        """Remove all history entries and save."""
        self._entries.clear()
        self._save_history()
        return self

    def remove(self, indices: Sequence[int]) -> Self:
        """Remove entries at the given indices and save."""
        for idx in sorted(indices, reverse=True):
            if 0 <= idx < len(self._entries):
                del self._entries[idx]
        self._save_history()
        return self
