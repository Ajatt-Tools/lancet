import dataclasses
from typing import Any, Self
from collections.abc import Callable

from PyQt6.QtCore import QObject, pyqtSignal, QRunnable, pyqtSlot, QThreadPool

from lancet.ocr.manga_ocr_base import MangaOCRException


@dataclasses.dataclass(frozen=True)
class QThreadPoolResult[ResultType]:
    """Holds the result or error from a background QThreadPool operation."""

    result: ResultType | None = None
    error: Exception | None = None


class QThreadPoolSignals[ResultType](QObject):
    """Signals emitted by a QThreadPoolWorker when its operation completes."""

    finished = pyqtSignal(QThreadPoolResult)


class QThreadPoolWorker[ResultType](QRunnable):
    """A QRunnable that executes a callable on a QThreadPool thread and emits the result via signals."""

    def __init__(self, op: Callable[[], ResultType]) -> None:
        """Initialize the worker with the operation to run."""
        super().__init__()
        self._op = op
        self.signals = QThreadPoolSignals[ResultType]()

    @pyqtSlot()
    def run(self) -> None:
        """Execute the operation and emit the result or error through the finished signal."""
        try:
            result = self._op()
        except Exception as e:
            self.signals.finished.emit(QThreadPoolResult(error=e))
        else:
            self.signals.finished.emit(QThreadPoolResult(result=result))


class QThreadPoolOp[ResultType](QObject):
    """
    Helper to perform an operation on a background thread using QThreadPool.
    `success` will be called with the return value of op().
    If op() throws an exception, it will be passed to `failure`.
    """

    def __init__(self, *, parent: QObject, op: Callable[[], ResultType], threadpool: QThreadPool) -> None:
        """Initialize the operation."""
        super().__init__(parent)
        self._parent = parent
        self._op = op
        self._success = None
        self._failure = None
        self._threadpool = threadpool

    def success(self, success: Callable[[ResultType], Any]) -> Self:
        """Set the callback to invoke with the result when the operation succeeds."""
        self._success = success
        return self

    def failure(self, failure: Callable[[MangaOCRException], Any]) -> Self:
        """Set the callback to invoke with the exception when the operation fails."""
        self._failure = failure
        return self

    def _on_finished(self, result: QThreadPoolResult[ResultType]) -> None:
        """Dispatch the result to the appropriate success or failure callback."""
        if result.error:
            self._failure(result.error)
        else:
            self._success(result.result)

    def run_in_background(self) -> None:
        """Submit the operation to the thread pool for asynchronous execution."""
        if not self._success:
            raise MangaOCRException("success handler is not set")
        if not self._failure:
            raise MangaOCRException("failure handler is not set")
        worker = QThreadPoolWorker[ResultType](self._op)
        worker.signals.finished.connect(self._on_finished)
        self._threadpool.start(worker)
