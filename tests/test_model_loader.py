# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""
Tests for BackgroundModelLoader.on_config_changed.
"""

import concurrent.futures
import pathlib
import threading
import typing
from collections.abc import Callable, Iterator, Sequence

import pytest
from PIL import Image

from lancet.config import Config
from lancet.model_utils.base import LancetModel, ModelLoadRecipe, ModelName
from lancet.model_utils.model_loader import BackgroundModelLoader
from lancet.notifications import NotifySend
from lancet.ocr.manga_ocr_base import MangaOcrBase
from lancet.text_detector_client.text_detector_base import (
    ComicTextDetectorBase,
    SpeechBubbleResult,
)


class FakeMangaOcr(MangaOcrBase):
    """Minimal MangaOcrBase implementation used to verify reload behavior."""

    def __init__(self, model_name: str, force_cpu: bool) -> None:
        """Store the model settings represented by this fake."""
        self._model_name = model_name
        self._force_cpu = force_cpu

    @property
    def pretrained_model_name_or_path(self) -> str:
        """Return the configured fake model name."""
        return self._model_name

    @property
    def force_cpu(self) -> bool:
        """Return whether CPU inference is forced."""
        return self._force_cpu

    def recognize(self, img_or_path: str | pathlib.Path | Image.Image) -> str:
        """Return an empty recognition result without loading a model."""
        return ""


class FakeTextDetector(ComicTextDetectorBase):
    """Minimal ComicTextDetectorBase implementation used to verify reload behavior."""

    def __init__(self, force_cpu: bool, detector_input_size: int) -> None:
        """Store the detector settings represented by this fake."""
        self._force_cpu = force_cpu
        self._detector_input_size = detector_input_size

    @property
    def force_cpu(self) -> bool:
        """Return whether CPU inference is forced."""
        return self._force_cpu

    @property
    def detector_input_size(self) -> int:
        """Return the configured detector input size."""
        return self._detector_input_size

    def get_speech_bubbles(
        self,
        img_or_path: pathlib.Path | Image.Image,
        *,
        include_lines: bool = False,
        keep_undetected_mask: bool = True,
    ) -> SpeechBubbleResult:
        """Return an empty speech-bubble result without running detection."""
        return SpeechBubbleResult(version="", img_width=0, img_height=0)


class NotifySpy(NotifySend):
    """Stand-in for NotifySend that records each call without touching desktop notifications."""

    def __init__(self) -> None:
        """Initialize recorded messages and completion synchronization."""
        # Skip NotifySend.__init__ entirely; we only need to record notify() calls.
        self.messages: list[str] = []
        self._condition = threading.Condition()

    def notify(self, msg: str) -> "NotifySpy":
        """Record a notification and wake completion waiters."""
        with self._condition:
            self.messages.append(msg)
            self._condition.notify_all()
        return self

    def set_duration(self, duration_sec: int) -> "NotifySpy":
        """Ignore notification duration changes and return self."""
        return self

    def wait_until_settled(self, loader: BackgroundModelLoader, *, timeout_sec: float = 5.0) -> None:
        """Wait until every model load has succeeded or failed."""
        with self._condition:
            if not self._condition.wait_for(lambda: loader.status().all_settled, timeout=timeout_sec):
                raise AssertionError("loader did not settle within timeout")


class CountingOp:
    """Wraps a recipe op so we can count invocations and inject failures by call index."""

    def __init__(self, builder: Callable[[], LancetModel], fail_on_call: Sequence[int]) -> None:
        """Store the model builder and call indexes that should fail."""
        self._builder = builder
        self._fail_on_call = frozenset(fail_on_call)
        self._call_count = 0
        self._lock = threading.Lock()

    @property
    def call_count(self) -> int:
        """Return the thread-safe invocation count."""
        with self._lock:
            return self._call_count

    def __call__(self) -> LancetModel:
        """Count the invocation, optionally fail, and otherwise build a model."""
        with self._lock:
            idx = self._call_count
            self._call_count += 1
        if idx in self._fail_on_call:
            raise RuntimeError(f"forced failure on call #{idx}")
        return self._builder()


def make_manga_ocr_op(cfg: Config, *, fail_on_call: Sequence[int] = ()) -> CountingOp:
    """Build a counting recipe op that constructs FakeMangaOcr from cfg."""
    return CountingOp(
        builder=lambda: FakeMangaOcr(model_name=cfg.huggingface_model_name, force_cpu=cfg.force_cpu),
        fail_on_call=fail_on_call,
    )


def make_text_detector_op(cfg: Config, *, fail_on_call: Sequence[int] = ()) -> CountingOp:
    """Build a counting recipe op that constructs FakeTextDetector from cfg."""
    return CountingOp(
        builder=lambda: FakeTextDetector(force_cpu=cfg.force_cpu, detector_input_size=cfg.text_detection_resolution),
        fail_on_call=fail_on_call,
    )


def build_loader(
    cfg: Config,
    *,
    notify: NotifySpy,
    executor: concurrent.futures.ThreadPoolExecutor,
    manga: CountingOp,
    text: CountingOp,
) -> BackgroundModelLoader:
    """Build a BackgroundModelLoader wired to the given counting recipe ops."""
    return BackgroundModelLoader(
        cfg=cfg,
        notify=notify,
        executor=executor,
        recipes=[
            ModelLoadRecipe(name=ModelName.manga_ocr, op=manga),
            ModelLoadRecipe(name=ModelName.text_detector, op=text),
        ],
    )


@pytest.fixture
def executor() -> Iterator[concurrent.futures.ThreadPoolExecutor]:
    """Provide a small thread pool, shut down after each test."""
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=2)
    try:
        yield pool
    finally:
        pool.shutdown(wait=True)


class RetryScenario(typing.NamedTuple):
    """A scenario where one model fails initially and must reload after on_config_changed."""

    failing_model: ModelName
    """The model whose first load is forced to fail."""


RETRY_SCENARIOS: dict[str, RetryScenario] = {
    "failed_manga_ocr_retries_on_config_changed": RetryScenario(failing_model=ModelName.manga_ocr),
    "failed_text_detector_retries_on_config_changed": RetryScenario(failing_model=ModelName.text_detector),
}


class TestOnConfigChangedRetriesAfterFailure:
    """A previously failed model must reload when on_config_changed fires."""

    @pytest.mark.parametrize("scenario", RETRY_SCENARIOS.values(), ids=RETRY_SCENARIOS.keys())
    def test_failed_model_retries_on_config_changed(
        self, scenario: RetryScenario, executor: concurrent.futures.ThreadPoolExecutor
    ) -> None:
        """If the first load of the failing model fails, on_config_changed must retry it."""
        cfg = Config()
        notify = NotifySpy()
        manga = make_manga_ocr_op(cfg, fail_on_call=(0,) if scenario.failing_model == ModelName.manga_ocr else ())
        text = make_text_detector_op(
            cfg, fail_on_call=(0,) if scenario.failing_model == ModelName.text_detector else ()
        )
        loader = build_loader(cfg, notify=notify, executor=executor, manga=manga, text=text)

        loader.load_all()
        notify.wait_until_settled(loader)
        assert not loader.is_model_ready(scenario.failing_model)

        loader.on_config_changed()
        notify.wait_until_settled(loader)

        assert loader.is_model_ready(scenario.failing_model)
        failing_op = manga if scenario.failing_model == ModelName.manga_ocr else text
        assert failing_op.call_count == 2  # Initial failed call + retry.


class ParameterChangeScenario(typing.NamedTuple):
    """A scenario where a config edit triggers reload(s) of one or both models."""

    config_mutator: Callable[[Config], None]
    expected_manga_calls: int
    expected_text_calls: int


PARAMETER_CHANGE_SCENARIOS: dict[str, ParameterChangeScenario] = {
    "no_change_does_not_reload": ParameterChangeScenario(
        config_mutator=lambda cfg: None,
        expected_manga_calls=1,
        expected_text_calls=1,
    ),
    "model_name_change_reloads_manga_only": ParameterChangeScenario(
        config_mutator=lambda cfg: setattr(cfg, "huggingface_model_name", "another/model"),
        expected_manga_calls=2,
        expected_text_calls=1,
    ),
    "force_cpu_change_reloads_both": ParameterChangeScenario(
        config_mutator=lambda cfg: setattr(cfg, "force_cpu", not cfg.force_cpu),
        expected_manga_calls=2,
        expected_text_calls=2,
    ),
    "resolution_change_reloads_text_only": ParameterChangeScenario(
        config_mutator=lambda cfg: setattr(cfg, "text_detection_resolution", 512),
        expected_manga_calls=1,
        expected_text_calls=2,
    ),
}


class TestOnConfigChangedReloadsOnParameterChange:
    """on_config_changed reloads only the models whose observed parameters have changed."""

    @pytest.mark.parametrize("scenario", PARAMETER_CHANGE_SCENARIOS.values(), ids=PARAMETER_CHANGE_SCENARIOS.keys())
    def test_parameter_change(
        self, scenario: ParameterChangeScenario, executor: concurrent.futures.ThreadPoolExecutor
    ) -> None:
        """Each scenario exercises a single config edit and verifies reload counts."""
        cfg = Config()
        notify = NotifySpy()
        manga = make_manga_ocr_op(cfg)
        text = make_text_detector_op(cfg)
        loader = build_loader(cfg, notify=notify, executor=executor, manga=manga, text=text)

        loader.load_all()
        notify.wait_until_settled(loader)
        assert manga.call_count == 1
        assert text.call_count == 1

        scenario.config_mutator(cfg)
        loader.on_config_changed()
        notify.wait_until_settled(loader)

        assert manga.call_count == scenario.expected_manga_calls
        assert text.call_count == scenario.expected_text_calls
