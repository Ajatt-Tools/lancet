# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import concurrent.futures
import threading
import typing
from collections.abc import Sequence

from loguru import logger

from lancet.config import Config
from lancet.model_utils.base import (
    LancetModel,
    ModelLoadError,
    ModelLoaderStatus,
    ModelLoadRecipe,
    ModelName,
)
from lancet.notifications import NotifySend
from lancet.ocr.manga_ocr_base import (
    MangaOcrBase,
    MangaOCRUnavailableError,
)
from lancet.ocr.thread_op import LancetThreadOp
from lancet.text_detector_client.text_detector_base import (
    ComicTextDetectorBase,
    ComicTextDetectorUnavailableError,
)


class BackgroundModelLoader:
    """Loads models in parallel background threads, fires one notification when all complete."""

    _recipes_by_name: dict[ModelName, ModelLoadRecipe]

    _ocr: MangaOcrBase | None
    _text_detector: ComicTextDetectorBase | None

    _models: dict[ModelName, LancetModel]
    _errors: dict[ModelName, Exception]

    def __init__(
        self,
        *,
        cfg: Config,
        notify: NotifySend,
        executor: concurrent.futures.ThreadPoolExecutor,
        recipes: Sequence[ModelLoadRecipe],
    ) -> None:
        """Initialize the loader with notification handler, thread pool, and model recipes."""
        self._cfg = cfg
        self._notify = notify
        self._executor = executor
        # Factories that load models.
        self._recipes_by_name = {r.name: r for r in recipes}
        # Current state
        self._models = {}
        self._errors = {}
        # Supported models:
        self._ocr = None
        self._text_detector = None

    @property
    def ocr(self) -> MangaOcrBase:
        """Return the OCR model, or None if not loaded."""
        if self._ocr is None:
            raise MangaOCRUnavailableError("OCR model is not loaded")
        return self._ocr

    @property
    def text_detector(self) -> ComicTextDetectorBase:
        """Return the text detector, or None if not loaded."""
        if self._text_detector is None:
            raise ComicTextDetectorUnavailableError("Text detector is not loaded")
        return self._text_detector

    @classmethod
    def new(
        cls,
        *,
        cfg: Config,
        notify: NotifySend,
        executor: concurrent.futures.ThreadPoolExecutor,
    ) -> typing.Self:
        # Have a lock ensure that pytorch is not imported twice at the same time.
        torch_lock = threading.Lock()

        def init_manga_ocr() -> MangaOcrBase:
            with torch_lock:
                from lancet.ocr.manga_ocr import MangaOcr

                return MangaOcr(
                    pretrained_model_name_or_path=cfg.huggingface_model_name,
                    force_cpu=cfg.force_cpu,
                )

        def init_text_detector() -> ComicTextDetectorBase:
            with torch_lock:
                from lancet.text_detector_client.text_detector import ComicTextDetector

                return ComicTextDetector(
                    force_cpu=cfg.force_cpu,
                    detector_input_size=cfg.text_detection_resolution,
                )

        return cls(
            cfg=cfg,
            notify=notify,
            executor=executor,
            recipes=[
                ModelLoadRecipe(
                    ModelName.manga_ocr,
                    op=init_manga_ocr,
                ),
                ModelLoadRecipe(
                    ModelName.text_detector,
                    op=init_text_detector,
                ),
            ],
        )

    def on_config_changed(self) -> None:
        """Update model configuration and reload the model in the background if it changed."""
        try:
            reload_needed = (
                self.ocr.pretrained_model_name_or_path != self._cfg.huggingface_model_name
                or self.ocr.force_cpu != self._cfg.force_cpu
            )
            if reload_needed:
                logger.info(
                    f"OCR config changed, reloading model: {self._cfg.huggingface_model_name}, force_cpu={self._cfg.force_cpu}"
                )
                self.reload_model_by_name(ModelName.manga_ocr)
        except MangaOCRUnavailableError:
            pass

        try:
            reload_needed = (
                self.text_detector.force_cpu != self._cfg.force_cpu
                or self.text_detector.detector_input_size != self._cfg.text_detection_resolution
            )
            if reload_needed:
                logger.info(f"Comic Text Detector config changed, reloading with force_cpu={self._cfg.force_cpu}")
                self.reload_model_by_name(ModelName.text_detector)
        except ComicTextDetectorUnavailableError:
            pass

    def is_model_ready(self, *names: ModelName) -> bool:
        """Return whether a specific model has loaded successfully."""
        return all(name in self._models for name in names)

    def load_all(self) -> None:
        """Submit all recipes to the executor."""
        for recipe in self._recipes_by_name.values():
            self._submit_recipe(recipe)

    def reload_model_by_name(self, name: ModelName) -> None:
        """Reload a single model by name using its stored recipe."""
        self._models.pop(name, None)
        self._errors.pop(name, None)
        self._clear_typed_field(name)
        self._submit_recipe(self._recipes_by_name[name])

    def status(self) -> ModelLoaderStatus:
        """Return current loading status."""
        return ModelLoaderStatus(
            total_count=len(self._recipes_by_name),
            ready_count=len(self._models),
            errors=frozenset(ModelLoadError(name=name, error=err) for name, err in self._errors.items()),
        )

    def _clear_typed_field(self, name: ModelName) -> None:
        """Reset the typed field for the given model name."""
        match name:
            case ModelName.manga_ocr:
                self._ocr = None
            case ModelName.text_detector:
                self._text_detector = None

    def _submit_recipe(self, recipe: ModelLoadRecipe) -> None:
        """Submit a recipe to the executor with unified callbacks."""

        def on_success(model: LancetModel) -> None:
            logger.info(f"Loaded model: {recipe.name}")
            self._models[recipe.name] = model
            self._store_model(model)
            self._check_all_done()

        def on_failed(e: Exception) -> None:
            logger.error(f"Failed to load {recipe.name}: {e}")
            self._errors[recipe.name] = e
            self._check_all_done()

        (
            LancetThreadOp[LancetModel](op=recipe.op, executor=self._executor)
            .success(on_success)
            .failure(on_failed)
            .run_in_background()
        )

    def _store_model(self, model: LancetModel) -> None:
        """Store a loaded model in the appropriate typed field."""
        match model:
            case MangaOcrBase():
                self._ocr = model
            case ComicTextDetectorBase():
                self._text_detector = model
            case _:
                logger.warning(f"Unknown model type: {type(model).__name__}")

    def _check_all_done(self) -> None:
        """Fire one notification when all recipes have completed (success or failure)."""
        if self.status().any_loading:
            # Still waiting.
            return
        self._notify.notify(self.status().what())
