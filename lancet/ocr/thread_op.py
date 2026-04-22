# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import concurrent.futures
from collections.abc import Callable
from typing import Any, Self

from lancet.ocr.manga_ocr_base import MangaOCRException


class LancetThreadOp[ResultType]:
    """
    Helper to perform an operation on a background thread using Python's ThreadPoolExecutor.
    `success` will be called with the return value of op().
    If op() throws an exception, it will be passed to `failure`.
    Both callbacks are invoked from the worker thread.
    """

    def __init__(
        self,
        *,
        op: Callable[[], ResultType],
        executor: concurrent.futures.ThreadPoolExecutor,
    ) -> None:
        """Initialize the operation."""
        self._op = op
        self._executor = executor
        self._success: Callable[[ResultType], Any] | None = None
        self._failure: Callable[[Exception], Any] | None = None

    def success(self, success: Callable[[ResultType], Any]) -> Self:
        """Set the callback to invoke with the result when the operation succeeds."""
        self._success = success
        return self

    def failure(self, failure: Callable[[Exception], Any]) -> Self:
        """Set the callback to invoke with the exception when the operation fails."""
        self._failure = failure
        return self

    def _on_done(self, future: concurrent.futures.Future[ResultType]) -> None:
        """Dispatch the result to the appropriate success or failure callback."""
        assert self._success is not None
        assert self._failure is not None
        try:
            self._success(future.result())
        except Exception as e:
            self._failure(e)

    def run_in_background(self) -> None:
        """Submit the operation to the thread pool for asynchronous execution."""
        if self._success is None:
            raise MangaOCRException("success handler is not set")
        if self._failure is None:
            raise MangaOCRException("failure handler is not set")
        future = self._executor.submit(self._op)
        future.add_done_callback(self._on_done)
