# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Tests for GoldenDict resolution and OCR workflow result delivery."""

import concurrent.futures
import typing
from unittest.mock import MagicMock, create_autospec, patch

import pytest
from PyQt6.QtWidgets import QApplication

from lancet.config import Config, OcrDestination
from lancet.model_utils.model_loader import BackgroundModelLoader
from lancet.model_utils.ocr_service import OcrService
from lancet.model_utils.ocr_workflow import OcrWorkflow, resolve_goldendict_path
from lancet.notifications import NotifySend
from lancet.ocr_history import OcrHistory


class GoldenDictPathScenario(typing.NamedTuple):
    """A configured path, resolver result, and expected executable."""

    path_override: str
    resolved_path: str | None
    expected_lookup: str
    expected_path: str


GOLDENDICT_PATH_SCENARIOS: dict[str, GoldenDictPathScenario] = {
    "configured_path_resolves": GoldenDictPathScenario(
        path_override="  custom-goldendict  ",
        resolved_path="/opt/goldendict/goldendict",
        expected_lookup="custom-goldendict",
        expected_path="/opt/goldendict/goldendict",
    ),
    "unresolved_configured_path_is_preserved": GoldenDictPathScenario(
        path_override="  /custom/goldendict  ",
        resolved_path=None,
        expected_lookup="/custom/goldendict",
        expected_path="/custom/goldendict",
    ),
    "empty_configuration_auto_detects": GoldenDictPathScenario(
        path_override="  ",
        resolved_path="/usr/bin/goldendict",
        expected_lookup="goldendict",
        expected_path="/usr/bin/goldendict",
    ),
    "failed_auto_detection_uses_command_name": GoldenDictPathScenario(
        path_override="",
        resolved_path=None,
        expected_lookup="goldendict",
        expected_path="goldendict",
    ),
}


class TestResolveGoldenDictPath:
    """Test configured and automatic GoldenDict executable resolution."""

    @pytest.mark.parametrize("scenario", GOLDENDICT_PATH_SCENARIOS.values(), ids=GOLDENDICT_PATH_SCENARIOS.keys())
    def test_resolution(self, scenario: GoldenDictPathScenario) -> None:
        """Resolve one candidate and preserve unresolved configured paths."""
        with patch(
            "lancet.model_utils.ocr_workflow.resolve_executable_with_fallbacks",
            autospec=True,
            return_value=scenario.resolved_path,
        ) as resolve:
            result = resolve_goldendict_path(scenario.path_override)
        assert result == scenario.expected_path
        resolve.assert_called_once_with(scenario.expected_lookup)


class OcrWorkflowContext(typing.NamedTuple):
    """An OCR workflow and its mocked notification service."""

    workflow: OcrWorkflow
    notify: MagicMock


def create_ocr_workflow_context(app: QApplication, cfg: Config) -> OcrWorkflowContext:
    """Construct an OCR workflow using autospecced collaborators."""
    notify = create_autospec(NotifySend, instance=True)
    return OcrWorkflowContext(
        workflow=OcrWorkflow(
            app=app,
            cfg=cfg,
            loader=create_autospec(BackgroundModelLoader, instance=True),
            ocr_service=create_autospec(OcrService, instance=True),
            notify=notify,
            history=create_autospec(OcrHistory, instance=True),
            executor=create_autospec(concurrent.futures.ThreadPoolExecutor, instance=True),
        ),
        notify=notify,
    )


class GoldenDictLaunchScenario(typing.NamedTuple):
    """A GoldenDict launch outcome and expected notification."""

    launch_error_type: type[OSError] | None
    launch_error_message: str
    expected_notification: str


GOLDENDICT_LAUNCH_SCENARIOS: dict[str, GoldenDictLaunchScenario] = {
    "success": GoldenDictLaunchScenario(
        launch_error_type=None,
        launch_error_message="",
        expected_notification="OCR result copied: recognized text",
    ),
    "executable_not_found": GoldenDictLaunchScenario(
        launch_error_type=FileNotFoundError,
        launch_error_message="missing executable",
        expected_notification="Executable not found: '/resolved/goldendict'. Check Preferences or PATH.",
    ),
    "other_os_error": GoldenDictLaunchScenario(
        launch_error_type=PermissionError,
        launch_error_message="permission denied",
        expected_notification="Failed to launch GoldenDict: permission denied",
    ),
}


def assert_goldendict_delivery(
    context: OcrWorkflowContext,
    scenario: GoldenDictLaunchScenario,
    *,
    resolve: MagicMock,
    run: MagicMock,
) -> None:
    """Assert GoldenDict resolution, launch, and notification for one scenario."""
    resolve.assert_called_once_with("/configured/goldendict")
    run.assert_called_once_with(("/resolved/goldendict", "recognized text"))
    context.notify.notify.assert_called_once_with(scenario.expected_notification)


class TestGoldenDictDelivery:
    """Test GoldenDict invocation with unittest.mock.patch."""

    @pytest.mark.parametrize("scenario", GOLDENDICT_LAUNCH_SCENARIOS.values(), ids=GOLDENDICT_LAUNCH_SCENARIOS.keys())
    def test_copy_ocr_result(self, scenario: GoldenDictLaunchScenario, qapp: QApplication) -> None:
        """Invoke GoldenDict with the resolved path and report exactly one result."""
        context = create_ocr_workflow_context(
            qapp,
            Config(copy_to=OcrDestination.goldendict, path_to_goldendict_executable="/configured/goldendict"),
        )
        with (
            patch(
                "lancet.model_utils.ocr_workflow.resolve_goldendict_path",
                autospec=True,
                return_value="/resolved/goldendict",
            ) as resolve,
            patch(
                "lancet.model_utils.ocr_workflow.run_and_disown",
                autospec=True,
                side_effect=(
                    scenario.launch_error_type(scenario.launch_error_message) if scenario.launch_error_type else None
                ),
            ) as run,
        ):
            context.workflow.copy_ocr_result("recognized text")
        assert_goldendict_delivery(context, scenario, resolve=resolve, run=run)


CLIPBOARD_SCENARIOS: dict[str, str] = {"recognized_text": "clipboard result"}


class TestClipboardDelivery:
    """Test clipboard OCR delivery."""

    @pytest.mark.parametrize("text", CLIPBOARD_SCENARIOS.values(), ids=CLIPBOARD_SCENARIOS.keys())
    def test_copy_ocr_result(self, text: str, qapp: QApplication) -> None:
        """Clipboard delivery writes text and reports success."""
        context = create_ocr_workflow_context(qapp, Config(copy_to=OcrDestination.clipboard))
        context.workflow.copy_ocr_result(text)
        clipboard = qapp.clipboard()
        assert clipboard is not None
        assert clipboard.text() == text
        context.notify.notify.assert_called_once_with(f"OCR result copied: {text}")
