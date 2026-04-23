# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import abc
import enum
import typing
from collections.abc import Collection
from collections.abc import Callable


class LancetModel(abc.ABC):
    """Base class for all models loaded by the background model loader."""

    pass


class ModelName(enum.StrEnum):
    """Identifiers for models managed by the background model loader."""

    manga_ocr = "manga_ocr"
    text_detector = "text_detector"


class ModelLoadRecipe(typing.NamedTuple):
    """A recipe for loading a model in a background thread."""

    name: ModelName
    op: Callable[[], LancetModel]


class ModelLoadError(typing.NamedTuple):
    name: ModelName
    error: Exception


class ModelLoaderStatus(typing.NamedTuple):
    """Status of the background model loader."""

    total_count: int
    ready_count: int
    errors: Collection[ModelLoadError]

    @property
    def all_ready(self) -> bool:
        """Return true if all models have loaded successfully."""
        return self.ready_count == self.total_count and not self.errors

    @property
    def any_loading(self) -> bool:
        """Return true if some models are still loading."""
        return not self.all_settled

    @property
    def all_settled(self) -> bool:
        """Return true if all models either failed or succeeded."""
        return self.total_count == self.ready_count + len(self.errors)

    def what(self) -> str:
        """Return a human-readable status message."""
        if self.all_ready:
            return "OCR ready."
        if self.errors:
            return " ".join(f"{name}: {err}." for name, err in self.errors.items())
        return "Models are loading..."
