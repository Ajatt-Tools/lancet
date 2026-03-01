import dataclasses
from typing import Callable, Any, Self

from PyQt6.QtCore import QObject, pyqtSignal, QRunnable, pyqtSlot, QThreadPool


class MangaOCRException(Exception):
    pass


@dataclasses.dataclass(frozen=True)
class QThreadPoolResult[ResultType]:
    result: ResultType | None = None
    error: MangaOCRException | None = None


class QThreadPoolSignals[ResultType](QObject):
    finished = pyqtSignal(QThreadPoolResult)


class QThreadPoolWorker[ResultType](QRunnable):
    def __init__(self, op: Callable[[], ResultType]) -> None:
        super().__init__()
        self._op = op
        self.signals = QThreadPoolSignals[ResultType]()

    @pyqtSlot()
    def run(self) -> None:
        try:
            result = self._op()
        except MangaOCRException as e:
            self.signals.finished.emit(QThreadPoolResult(error=e))
        else:
            self.signals.finished.emit(QThreadPoolResult(result=result))


class QThreadPoolOp[ResultType](QObject):
    """
    Helper to perform an operation on a background thread using QThreadPool.
    `success` will be called with the return value of op().
    If op() throws an exception, it will be passed to `failure`.
    """

    def __init__(self, *, parent: QObject, op: Callable[[], ResultType], threadpool: QThreadPool):
        super().__init__(parent)
        self._parent = parent
        self._op = op
        self._success = None
        self._failure = None
        self._threadpool = threadpool

    def success(self, success: Callable[[ResultType], Any]) -> Self:
        self._success = success
        return self

    def failure(self, failure: Callable[[MangaOCRException], Any]) -> Self:
        self._failure = failure
        return self

    def _on_finished(self, result: QThreadPoolResult[ResultType]) -> None:
        if result.error:
            self._failure(result.error)
        else:
            self._success(result.result)

    def run_in_background(self) -> None:
        worker = QThreadPoolWorker[ResultType](self._op)
        worker.signals.finished.connect(self._on_finished)
        self._threadpool.start(worker)
