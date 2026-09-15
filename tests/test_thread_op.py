# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Tests for worker execution and Qt-thread callback dispatch in LancetThreadOp."""

import concurrent.futures
import enum
import threading
import typing
from collections.abc import Iterator
from unittest.mock import call, patch

import pytest
from PyQt6.QtCore import QEventLoop, QThread
from PyQt6.QtWidgets import QApplication

from lancet.ocr.manga_ocr_base import MangaOCRException
from lancet.ocr.thread_op import LancetThreadOp
from tests.helpers import wait_for_qt_event_loop


class DispatchVerdict(enum.StrEnum):
    """The worker result path expected by one dispatch scenario."""

    success = "success"
    failure = "failure"


class DispatchScenario(typing.NamedTuple):
    """A worker verdict and, for failure, fresh exception construction metadata."""

    verdict: DispatchVerdict
    error_type: type[Exception] | None
    error_message: str


DISPATCH_SCENARIOS: dict[str, DispatchScenario] = {
    "success": DispatchScenario(verdict=DispatchVerdict.success, error_type=None, error_message=""),
    "operation_failure": DispatchScenario(
        verdict=DispatchVerdict.failure,
        error_type=RuntimeError,
        error_message="operation failed",
    ),
}


TEMPORARY_OPERATION_SCENARIOS: dict[str, DispatchScenario] = {
    "temporary_success_operation": DispatchScenario(verdict=DispatchVerdict.success, error_type=None, error_message=""),
}


class HandlerRequirement(enum.StrEnum):
    """The required LancetThreadOp callback intentionally omitted by a scenario."""

    success = "success"
    failure = "failure"


class MissingHandlerScenario(typing.NamedTuple):
    """One required callback omitted before background execution begins."""

    missing: HandlerRequirement
    expected_error: str


MISSING_HANDLER_SCENARIOS: dict[str, MissingHandlerScenario] = {
    "success_handler": MissingHandlerScenario(
        missing=HandlerRequirement.success,
        expected_error="success handler is not set",
    ),
    "failure_handler": MissingHandlerScenario(
        missing=HandlerRequirement.failure,
        expected_error="failure handler is not set",
    ),
}


class CallbackFailureScenario(typing.NamedTuple):
    """A success-callback error expected to be logged without failure rerouting."""

    error_message: str


CALLBACK_FAILURE_SCENARIOS: dict[str, CallbackFailureScenario] = {
    "success_callback_error": CallbackFailureScenario(error_message="callback failed"),
}


class CallbackRecorder:
    """Record one completion callback and exit its nested Qt event loop."""

    def __init__(self, loop: QEventLoop) -> None:
        """Store the event loop that callback completion should exit."""
        self._loop = loop
        self._success_value: int | None = None
        self._failure: Exception | None = None
        self._callback_thread: QThread | None = None

    @property
    def success_value(self) -> int | None:
        """Return the integer produced by a successful operation, if any."""
        return self._success_value

    @property
    def failure(self) -> Exception | None:
        """Return the operation failure delivered to the callback, if any."""
        return self._failure

    @property
    def callback_thread(self) -> QThread | None:
        """Return the Qt thread that ran the most recent completion callback."""
        return self._callback_thread

    def on_success(self, value: int) -> None:
        """Record a successful value and the callback's Qt thread."""
        self._success_value = value
        self._callback_thread = QThread.currentThread()
        self._loop.quit()

    def on_failure(self, error: Exception) -> None:
        """Record a failed operation and the callback's Qt thread."""
        self._failure = error
        self._callback_thread = QThread.currentThread()
        self._loop.quit()


class WorkerThreadId:
    """Return the Python thread ID executing the background operation."""

    def __call__(self) -> int:
        """Return the current worker thread ID."""
        return threading.get_ident()


class FailingOperation:
    """Raise one caller-owned error from the executor thread."""

    def __init__(self, error: Exception) -> None:
        """Store the exact exception that the worker must raise."""
        self._error = error

    def __call__(self) -> int:
        """Raise the configured failure without wrapping or replacing it."""
        raise self._error


class ExplodingSuccess:
    """Exit the event loop and then raise from a success callback."""

    def __init__(self, loop: QEventLoop, error_message: str) -> None:
        """Store the loop and callback error message for one logging scenario."""
        self._loop = loop
        self._error_message = error_message
        self._was_called = False

    @property
    def was_called(self) -> bool:
        """Return whether the exploding success callback ran."""
        return self._was_called

    def __call__(self, value: int) -> None:
        """Exit the loop and raise to verify callback failures are logged separately."""
        self._was_called = True
        self._loop.quit()
        raise RuntimeError(self._error_message)


class ExplodingFailure:
    """Exit the event loop and then raise from a failure callback."""

    def __init__(self, loop: QEventLoop, error_message: str) -> None:
        """Store the loop and callback error message for one logging scenario."""
        self._loop = loop
        self._error_message = error_message
        self._was_called = False

    @property
    def was_called(self) -> bool:
        """Return whether the exploding failure callback ran."""
        return self._was_called

    def __call__(self, _: Exception) -> None:
        """Exit the loop and raise to verify failure callback errors are logged separately."""
        self._was_called = True
        self._loop.quit()
        raise RuntimeError(self._error_message)


class TrackingThreadOp(LancetThreadOp[int]):
    """Expose whether dispatched operations request deferred QObject deletion."""

    def __init__(
        self, *, op: WorkerThreadId | FailingOperation, executor: concurrent.futures.ThreadPoolExecutor
    ) -> None:
        """Initialize one trackable integer operation."""
        self._delete_later_called = False
        super().__init__(op=op, executor=executor)

    @property
    def delete_later_called(self) -> bool:
        """Return whether the completion dispatcher requested QObject cleanup."""
        return self._delete_later_called

    def deleteLater(self) -> None:  # noqa: N802
        """Record deferred deletion before delegating to QObject."""
        self._delete_later_called = True
        super().deleteLater()


@pytest.fixture
def executor() -> Iterator[concurrent.futures.ThreadPoolExecutor]:
    """Provide one worker for deterministic thread identity checks."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        yield pool


class TestLancetThreadOp:
    """Test executor work, Qt-main-thread dispatch, validation, logging, and cleanup."""

    @pytest.mark.parametrize("scenario", DISPATCH_SCENARIOS.values(), ids=DISPATCH_SCENARIOS.keys())
    def test_dispatches_outcome_on_main_thread(
        self, scenario: DispatchScenario, executor: concurrent.futures.ThreadPoolExecutor, qapp: QApplication
    ) -> None:
        """Worker outcomes preserve their verdict and reach callbacks on QApplication's Qt thread."""
        loop = QEventLoop()
        recorder = CallbackRecorder(loop)
        expected_error = scenario.error_type(scenario.error_message) if scenario.error_type else None
        operation = TrackingThreadOp(
            op=WorkerThreadId() if expected_error is None else FailingOperation(expected_error),
            executor=executor,
        )
        operation.success(recorder.on_success).failure(recorder.on_failure).run_in_background()
        wait_for_qt_event_loop(loop)
        assert recorder.callback_thread == qapp.thread()
        assert operation.delete_later_called
        if expected_error is None:
            assert recorder.failure is None
            assert recorder.success_value is not None
            assert recorder.success_value != threading.get_ident()
            return
        assert recorder.success_value is None
        assert recorder.failure is expected_error
        assert str(recorder.failure) == scenario.error_message

    @pytest.mark.parametrize(
        "scenario", TEMPORARY_OPERATION_SCENARIOS.values(), ids=TEMPORARY_OPERATION_SCENARIOS.keys()
    )
    def test_temporary_operation_survives_until_dispatch(
        self, scenario: DispatchScenario, executor: concurrent.futures.ThreadPoolExecutor, qapp: QApplication
    ) -> None:
        """Application parenting preserves a temporary fluent operation until its success callback runs."""
        loop = QEventLoop()
        recorder = CallbackRecorder(loop)
        assert scenario.verdict == DispatchVerdict.success
        LancetThreadOp(op=WorkerThreadId(), executor=executor).success(recorder.on_success).failure(
            recorder.on_failure
        ).run_in_background()
        wait_for_qt_event_loop(loop)
        assert recorder.failure is None
        assert recorder.success_value is not None
        assert recorder.callback_thread == qapp.thread()

    @pytest.mark.parametrize("scenario", MISSING_HANDLER_SCENARIOS.values(), ids=MISSING_HANDLER_SCENARIOS.keys())
    def test_rejects_missing_handler(
        self, scenario: MissingHandlerScenario, executor: concurrent.futures.ThreadPoolExecutor
    ) -> None:
        """Starting an operation without either required callback raises its exact public error."""
        recorder = CallbackRecorder(QEventLoop())
        operation = LancetThreadOp(op=WorkerThreadId(), executor=executor)
        match scenario.missing:
            case HandlerRequirement.success:
                operation.failure(recorder.on_failure)
            case HandlerRequirement.failure:
                operation.success(recorder.on_success)
        with pytest.raises(MangaOCRException) as exc_info:
            operation.run_in_background()
        assert str(exc_info.value) == scenario.expected_error

    def test_rejects_construction_without_application(self, executor: concurrent.futures.ThreadPoolExecutor) -> None:
        """A queued callback operation requires a live Qt application owner."""
        with patch("lancet.ocr.thread_op.QCoreApplication.instance", return_value=None):
            with pytest.raises(MangaOCRException) as exc_info:
                LancetThreadOp(op=WorkerThreadId(), executor=executor)

        assert str(exc_info.value) == "LancetThreadOp requires an active Qt application"

    @pytest.mark.parametrize("scenario", CALLBACK_FAILURE_SCENARIOS.values(), ids=CALLBACK_FAILURE_SCENARIOS.keys())
    def test_callback_failure_is_logged_without_failure_rerouting(
        self, scenario: CallbackFailureScenario, executor: concurrent.futures.ThreadPoolExecutor
    ) -> None:
        """A success callback bug is logged and does not invoke the worker failure callback."""
        loop = QEventLoop()
        success = ExplodingSuccess(loop, scenario.error_message)
        recorder = CallbackRecorder(loop)
        with patch("lancet.ocr.thread_op.logger.exception") as log:
            LancetThreadOp(op=WorkerThreadId(), executor=executor).success(success).failure(
                recorder.on_failure
            ).run_in_background()
            wait_for_qt_event_loop(loop)
        assert success.was_called
        assert recorder.failure is None
        assert log.call_args == call(f"LancetThreadOp completion callback failed: {scenario.error_message}")

    @pytest.mark.parametrize("scenario", CALLBACK_FAILURE_SCENARIOS.values(), ids=CALLBACK_FAILURE_SCENARIOS.keys())
    def test_failure_callback_error_is_logged(
        self, scenario: CallbackFailureScenario, executor: concurrent.futures.ThreadPoolExecutor
    ) -> None:
        """A failure callback bug is logged and does not invoke the success callback."""
        loop = QEventLoop()
        failure = ExplodingFailure(loop, scenario.error_message)
        recorder = CallbackRecorder(loop)
        error = RuntimeError("operation failed")
        with patch("lancet.ocr.thread_op.logger.exception") as log:
            TrackingThreadOp(op=FailingOperation(error), executor=executor).success(recorder.on_success).failure(
                failure
            ).run_in_background()
            wait_for_qt_event_loop(loop)

        assert failure.was_called
        assert recorder.success_value is None
        assert log.call_args == call(f"LancetThreadOp completion callback failed: {scenario.error_message}")
