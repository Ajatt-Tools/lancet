# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import concurrent.futures
import typing
from collections.abc import Callable
from typing import Self

from loguru import logger
from PyQt6.QtCore import QCoreApplication, QObject, Qt, pyqtSignal, pyqtSlot
from zala.utils import q_emit

from lancet.ocr.manga_ocr_base import MangaOCRException


class ThreadOpResult(typing.NamedTuple):
    """The result or exception produced by a background operation."""

    result: object | None = None
    error: Exception | None = None


class LancetThreadOp[ResultType](QObject):
    """
    Run an operation in ThreadPoolExecutor and invoke completion callbacks on Qt's main thread.

    The operation itself never runs on a Qt thread. A queued signal carries its
    result to this QObject, which belongs to QCoreApplication's main thread.
    """

    _finished = pyqtSignal(ThreadOpResult)

    # Callbacks
    _success: Callable[[ResultType], None] | None
    _failure: Callable[[Exception], None] | None

    def __init__(
        self,
        *,
        op: Callable[[], ResultType],
        executor: concurrent.futures.ThreadPoolExecutor,
        app: QCoreApplication | None = None,
    ) -> None:
        """Initialize the operation and attach its lifetime to the active Qt application."""
        if not (app := app or QCoreApplication.instance()):
            raise MangaOCRException("LancetThreadOp requires an active Qt application")
        super().__init__(app)
        self._op = op
        self._executor = executor
        self._success = None
        self._failure = None
        self._finished.connect(self._dispatch_outcome, Qt.ConnectionType.QueuedConnection)  # type: ignore[call-arg]

    def success(self, success: Callable[[ResultType], None]) -> Self:
        """Set the callback to invoke with the result when the operation succeeds."""
        self._success = success
        return self

    def failure(self, failure: Callable[[Exception], None]) -> Self:
        """Set the callback to invoke with the exception when the operation fails."""
        self._failure = failure
        return self

    def _emit_future_outcome(self, future: concurrent.futures.Future[ResultType]) -> None:
        """Queue a completed future's outcome for main-thread callback dispatch."""
        try:
            outcome = ThreadOpResult(result=future.result())
        except Exception as error:
            outcome = ThreadOpResult(error=error)
        q_emit(self._finished, outcome)

    @pyqtSlot(ThreadOpResult)
    def _dispatch_outcome(self, outcome: ThreadOpResult) -> None:
        """Dispatch one worker outcome on the QObject's Qt main thread."""
        assert self._success is not None
        assert self._failure is not None
        try:
            if outcome.error is not None:
                self._failure(outcome.error)
            else:
                self._success(typing.cast(ResultType, outcome.result))
        except Exception as ex:
            logger.exception(f"LancetThreadOp completion callback failed: {ex}")
        finally:
            self.deleteLater()

    def run_in_background(self) -> None:
        """Submit this one-shot operation to the thread pool for asynchronous execution."""
        if self._success is None:
            raise MangaOCRException("success handler is not set")
        if self._failure is None:
            raise MangaOCRException("failure handler is not set")
        future = self._executor.submit(self._op)
        future.add_done_callback(self._emit_future_outcome)
