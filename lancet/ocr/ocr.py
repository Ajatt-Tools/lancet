# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
import pathlib
import typing

from PIL import Image
from PyQt6.QtCore import QThreadPool, QObject, pyqtSignal, QRunnable, pyqtSlot

from lancet.ocr.manga_ocr_launcher import MangaOCRLauncher, MangaOCRException


class OCRInitResult(typing.NamedTuple):
    launcher: MangaOCRLauncher | None = None
    exception: Exception | None = None


class OCRInitSignals(QObject):
    finished = pyqtSignal(OCRInitResult)


class OCRInitWorker(QRunnable):
    def __init__(self) -> None:
        super().__init__()
        self.signals = OCRInitSignals()

    @pyqtSlot()
    def run(self) -> None:
        try:
            launcher = MangaOCRLauncher()
            launcher.init_model()
        except Exception as e:
            self.signals.finished.emit(OCRInitResult(exception=e))
        else:
            self.signals.finished.emit(OCRInitResult(launcher=launcher))


class OCR(QObject):
    _ocr_model: MangaOCRLauncher | None = None
    _threadpool: QThreadPool

    init_finished = pyqtSignal(OCRInitResult)

    def __init__(self, threadpool: QThreadPool, parent=None):
        super().__init__(parent)
        self._ocr_model = None
        self._threadpool = threadpool

    def init_manga_ocr(self) -> None:
        worker = OCRInitWorker()
        worker.signals.finished.connect(self._on_ocr_model_ready)
        self._threadpool.start(worker)

    def _on_ocr_model_ready(self, model: OCRInitResult) -> None:
        if model.launcher:
            self._ocr_model = model.launcher
        self.init_finished.emit(model)


    def recognize(self, img_or_path: str | pathlib.Path | Image.Image) -> str:
        if self._ocr_model is None:
            raise MangaOCRException("ocr model should be initialized")
        return self._ocr_model.recognize(img_or_path)
