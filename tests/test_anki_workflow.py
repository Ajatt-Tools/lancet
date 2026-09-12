# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Tests for the asynchronous Anki screenshot workflow."""

import concurrent.futures
import functools
import typing
from collections.abc import Callable, Iterator
from unittest.mock import Mock, call, create_autospec, patch

import pytest
from PIL import Image
from PyQt6.QtCore import QEventLoop
from zala.config import ScreenshotPreviewOpts
from zala.exceptions import ZalaException
from zala.main_window import UserSelectionResult
from zala.take_region import ZalaTakeScreenRegion

from lancet.anki.client import AnkiConnectClient
from lancet.anki.image_types import AnkiImageFormat, EncodedImage, ImageParameters
from lancet.anki.workflow import AnkiWorkflow
from lancet.config import Config, make_preview_opts
from lancet.exceptions import AnkiConnectUnavailableError, PixmapConversionError
from lancet.notifications import NotifySend
from tests.helpers import wait_for_qt_event_loop

NOTE_ID = 42
IMAGE_FIELD = "Image"
ATTACHMENT_IMAGE = EncodedImage(
    data=b"image",
    image_format=AnkiImageFormat.avif,
    settings=ImageParameters(width=400, height=250, quality=33),
)


class AnkiWorkflowContext:
    """An Anki workflow with mocked UI collaborators and a real single-worker executor."""

    def __init__(self, cfg: Config) -> None:
        """Construct the workflow and its test collaborators."""
        self.cfg = cfg
        self.notify = create_autospec(NotifySend, instance=True)
        self.take = create_autospec(ZalaTakeScreenRegion, instance=True)
        self.client = typing.cast(Mock, create_autospec(AnkiConnectClient, instance=True))
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self.workflow = AnkiWorkflow(
            cfg, executor=self.executor, notify=self.notify, take=self.take, client=self.client
        )

    def __enter__(self) -> typing.Self:
        """Return this context while its executor is active."""
        return self

    def __exit__(self, *args: object) -> None:
        """Wait for and release the workflow executor."""
        self.executor.shutdown(wait=True)


class SelectionRecorder:
    """Record an Anki selection callback and exit when Zala selection opens."""

    def __init__(self, loop: QEventLoop) -> None:
        """Store the nested event loop that selection startup should exit."""
        self._loop = loop
        self.callback: Callable[[UserSelectionResult], None] | None = None
        self.options: ScreenshotPreviewOpts | None = None

    def __call__(self, *, on_finish: Callable[[UserSelectionResult], None], opts: ScreenshotPreviewOpts) -> None:
        """Record Zala's completion callback and options, then exit the event loop."""
        self.callback = on_finish
        self.options = opts
        self._loop.quit()


class NotificationRecorder:
    """Record one notification and exit after a queued workflow callback runs."""

    def __init__(self, loop: QEventLoop) -> None:
        """Store the event loop that notification delivery should exit."""
        self._loop = loop
        self.messages: list[str] = []

    def __call__(self, message: str) -> None:
        """Record a notification message and exit the nested event loop."""
        self.messages.append(message)
        self._loop.quit()


class AttachmentScenario(typing.NamedTuple):
    """Configuration and attachment result used for encoding propagation tests."""

    cfg: Config
    filename: str


ATTACHMENT_SCENARIOS: dict[str, AttachmentScenario] = {
    "configured_avif": AttachmentScenario(
        cfg=Config(
            anki_image_field=IMAGE_FIELD,
            anki_image_width=400,
            anki_image_height=250,
            anki_image_quality=33,
            anki_image_format=AnkiImageFormat.avif,
        ),
        filename="lancet.webp",
    ),
}


class CancellationScenario(typing.NamedTuple):
    """A selection-conversion error that must not submit attachment work."""

    error_type: type[PixmapConversionError]
    error_message: str
    expected_notification: str


CANCELLATION_SCENARIOS: dict[str, CancellationScenario] = {
    "selection_aborted": CancellationScenario(
        error_type=PixmapConversionError,
        error_message="Selection aborted",
        expected_notification="Anki attachment failed: Selection aborted",
    ),
}


class PreflightSelectionScenario(typing.NamedTuple):
    """A resolved note ID captured before Zala selection starts."""

    note_id: int


PREFLIGHT_SELECTION_SCENARIOS: dict[str, PreflightSelectionScenario] = {
    "stable_target": PreflightSelectionScenario(note_id=NOTE_ID),
}


class SelectionFailureScenario(typing.NamedTuple):
    """A Zala selection startup error and the public notification it produces."""

    error_type: type[ZalaException]
    error_message: str
    expected_notification: str


SELECTION_FAILURE_SCENARIOS: dict[str, SelectionFailureScenario] = {
    "zala_error": SelectionFailureScenario(
        error_type=ZalaException,
        error_message="selection failed",
        expected_notification="Anki attachment failed: selection failed",
    ),
}


class PreflightFailureScenario(typing.NamedTuple):
    """A note-resolution failure and the notification delivered from its queued callback."""

    error_type: type[Exception]
    error_message: str
    expected_notification: str


PREFLIGHT_FAILURE_SCENARIOS: dict[str, PreflightFailureScenario] = {
    "ankiconnect_unavailable": PreflightFailureScenario(
        error_type=AnkiConnectUnavailableError,
        error_message="connection refused",
        expected_notification="AnkiConnect isn't running.",
    ),
}


class FailureNotificationScenario(typing.NamedTuple):
    """A worker error and the concise notification expected for it."""

    error_type: type[Exception]
    error_message: str
    expected_notification: str


FAILURE_NOTIFICATION_SCENARIOS: dict[str, FailureNotificationScenario] = {
    "ankiconnect_unavailable": FailureNotificationScenario(
        error_type=AnkiConnectUnavailableError,
        error_message="connection refused details",
        expected_notification="AnkiConnect isn't running.",
    ),
    "other_failure": FailureNotificationScenario(
        error_type=RuntimeError,
        error_message="other failure",
        expected_notification="Anki attachment failed: other failure",
    ),
}


@pytest.fixture
def workflow_context() -> Iterator[AnkiWorkflowContext]:
    """Provide an Anki workflow and shut down its executor after the test."""
    with AnkiWorkflowContext(Config()) as context:
        yield context


class TestAnkiWorkflow:
    """Test Anki workflow conversion, target stability, and notification behavior."""

    @pytest.mark.parametrize("scenario", ATTACHMENT_SCENARIOS.values(), ids=ATTACHMENT_SCENARIOS.keys())
    def test_attach_image_uses_current_config(self, scenario: AttachmentScenario) -> None:
        """The worker receives the configured field, format, and non-swappable image parameters."""
        with AnkiWorkflowContext(scenario.cfg) as context:
            context.client.attach_image.return_value = scenario.filename
            with patch("lancet.anki.workflow.encode_image", return_value=ATTACHMENT_IMAGE) as encode:
                result = context.workflow._attach_image(NOTE_ID, Image.new("RGB", (800, 600)))
        assert encode.call_args.kwargs == {
            "image_format": AnkiImageFormat.avif,
            "settings": ImageParameters(width=400, height=250, quality=33),
        }
        assert context.client.attach_image.call_args.args == (NOTE_ID, IMAGE_FIELD, ATTACHMENT_IMAGE)
        assert result.note_id == NOTE_ID
        assert result.filename == scenario.filename

    @pytest.mark.parametrize(
        "scenario", PREFLIGHT_SELECTION_SCENARIOS.values(), ids=PREFLIGHT_SELECTION_SCENARIOS.keys()
    )
    def test_resolves_note_before_selection(
        self, scenario: PreflightSelectionScenario, workflow_context: AnkiWorkflowContext
    ) -> None:
        """Public preflight captures the target note and complete selection options before selection."""
        loop = QEventLoop()
        selection = SelectionRecorder(loop)
        workflow_context.client.last_added_note_id.return_value = scenario.note_id
        workflow_context.take.select_area.side_effect = selection
        workflow_context.workflow.screenshot_and_add_to_anki()
        wait_for_qt_event_loop(loop)
        assert workflow_context.client.last_added_note_id.call_count == 1
        assert isinstance(selection.callback, functools.partial)
        assert selection.callback.func == workflow_context.workflow._attach_selection
        assert selection.callback.args == (scenario.note_id,)
        assert selection.options == make_preview_opts(workflow_context.cfg)

    @pytest.mark.parametrize("scenario", CANCELLATION_SCENARIOS.values(), ids=CANCELLATION_SCENARIOS.keys())
    def test_cancelled_selection_notifies_without_submission(
        self, scenario: CancellationScenario, workflow_context: AnkiWorkflowContext
    ) -> None:
        """A conversion failure reports one error without submitting encoding or attachment work."""
        conversion_error = scenario.error_type(scenario.error_message)
        with (
            patch("lancet.anki.workflow.prepare_pillow_image", side_effect=conversion_error) as prepare,
            patch.object(workflow_context.executor, "submit", wraps=workflow_context.executor.submit) as submit,
        ):
            workflow_context.workflow._attach_selection(NOTE_ID, create_autospec(UserSelectionResult, instance=True))
        prepare.assert_called_once()
        submit.assert_not_called()
        workflow_context.client.attach_image.assert_not_called()
        workflow_context.notify.notify.assert_called_once_with(scenario.expected_notification)

    @pytest.mark.parametrize("scenario", ATTACHMENT_SCENARIOS.values(), ids=ATTACHMENT_SCENARIOS.keys())
    def test_successful_selection_submits_and_notifies(
        self, scenario: AttachmentScenario, workflow_context: AnkiWorkflowContext
    ) -> None:
        """A converted selection encodes, attaches, and reports its exact successful result."""
        loop = QEventLoop()
        notification = NotificationRecorder(loop)
        selection = create_autospec(UserSelectionResult, instance=True)
        workflow_context.client.attach_image.return_value = scenario.filename
        workflow_context.notify.notify.side_effect = notification
        with patch("lancet.anki.workflow.prepare_pillow_image", return_value=Image.new("RGB", (800, 600))):
            with patch("lancet.anki.workflow.encode_image", return_value=ATTACHMENT_IMAGE):
                workflow_context.workflow._attach_selection(NOTE_ID, selection)
                wait_for_qt_event_loop(loop)
        assert workflow_context.client.attach_image.call_args.args == (NOTE_ID, "Image", ATTACHMENT_IMAGE)
        assert notification.messages == [f"Added avif image to Anki note 42: {scenario.filename} (0.00 KiB)"]

    @pytest.mark.parametrize("scenario", PREFLIGHT_FAILURE_SCENARIOS.values(), ids=PREFLIGHT_FAILURE_SCENARIOS.keys())
    def test_preflight_failure_notifies_without_selection(
        self, scenario: PreflightFailureScenario, workflow_context: AnkiWorkflowContext
    ) -> None:
        """A queued note-resolution failure notifies without opening the region selector."""
        loop = QEventLoop()
        notification = NotificationRecorder(loop)
        workflow_context.notify.notify.side_effect = notification
        workflow_context.client.last_added_note_id.side_effect = scenario.error_type(scenario.error_message)
        workflow_context.workflow.screenshot_and_add_to_anki()
        wait_for_qt_event_loop(loop)
        assert workflow_context.take.select_area.call_count == 0
        assert notification.messages == [scenario.expected_notification]

    @pytest.mark.parametrize("scenario", SELECTION_FAILURE_SCENARIOS.values(), ids=SELECTION_FAILURE_SCENARIOS.keys())
    def test_selection_start_failure_notifies(
        self, scenario: SelectionFailureScenario, workflow_context: AnkiWorkflowContext
    ) -> None:
        """A Zala selection startup failure is converted to one public notification."""
        workflow_context.take.select_area.side_effect = scenario.error_type(scenario.error_message)
        workflow_context.workflow._start_anki_selection(NOTE_ID)
        workflow_context.notify.notify.assert_called_once_with(scenario.expected_notification)

    @pytest.mark.parametrize(
        "scenario", FAILURE_NOTIFICATION_SCENARIOS.values(), ids=FAILURE_NOTIFICATION_SCENARIOS.keys()
    )
    def test_failure_notification(
        self, scenario: FailureNotificationScenario, workflow_context: AnkiWorkflowContext
    ) -> None:
        """Connection details stay in logs while desktop notifications remain concise."""
        error = scenario.error_type(scenario.error_message)
        with patch("lancet.anki.workflow.logger.warning") as warning:
            workflow_context.workflow._notify_anki_failure(error)
        warning.assert_called_once_with(f"Anki attachment failed: {error}")
        workflow_context.notify.notify.assert_called_once_with(scenario.expected_notification)
