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
        "  custom-goldendict  ",
        "/opt/goldendict/goldendict",
        "custom-goldendict",
        "/opt/goldendict/goldendict",
    ),
    "unresolved_configured_path_is_preserved": GoldenDictPathScenario(
        "  /custom/goldendict  ", None, "/custom/goldendict", "/custom/goldendict"
    ),
    "empty_configuration_auto_detects": GoldenDictPathScenario(
        "  ", "/usr/bin/goldendict", "goldendict", "/usr/bin/goldendict"
    ),
    "failed_auto_detection_uses_command_name": GoldenDictPathScenario("", None, "goldendict", "goldendict"),
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


class WorkflowHarness(typing.NamedTuple):
    """An OCR workflow and its mocked notification service."""

    workflow: OcrWorkflow
    notify: MagicMock


def make_workflow(app: QApplication, cfg: Config) -> WorkflowHarness:
    """Construct an OCR workflow using autospecced collaborators."""
    notify = create_autospec(NotifySend, instance=True)
    return WorkflowHarness(
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

    launch_error: OSError | None
    expected_notification: str


GOLDENDICT_LAUNCH_SCENARIOS: dict[str, GoldenDictLaunchScenario] = {
    "success": GoldenDictLaunchScenario(None, "OCR result copied: recognized text"),
    "executable_not_found": GoldenDictLaunchScenario(
        FileNotFoundError("missing executable"),
        "Executable not found: '/resolved/goldendict'. Check Preferences or PATH.",
    ),
    "other_os_error": GoldenDictLaunchScenario(
        PermissionError("permission denied"), "Failed to launch GoldenDict: permission denied"
    ),
}


class TestGoldenDictDelivery:
    """Test GoldenDict invocation with unittest.mock.patch."""

    @pytest.mark.parametrize("scenario", GOLDENDICT_LAUNCH_SCENARIOS.values(), ids=GOLDENDICT_LAUNCH_SCENARIOS.keys())
    def test_copy_ocr_result(self, scenario: GoldenDictLaunchScenario, qapp: QApplication) -> None:
        """Invoke GoldenDict with the resolved path and report exactly one result."""
        harness = make_workflow(
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
                side_effect=scenario.launch_error,
            ) as run,
        ):
            harness.workflow.copy_ocr_result("recognized text")
        resolve.assert_called_once_with("/configured/goldendict")
        run.assert_called_once_with(("/resolved/goldendict", "recognized text"))
        harness.notify.notify.assert_called_once_with(scenario.expected_notification)


CLIPBOARD_SCENARIOS: dict[str, str] = {"recognized_text": "clipboard result"}


class TestClipboardDelivery:
    """Test clipboard OCR delivery."""

    @pytest.mark.parametrize("text", CLIPBOARD_SCENARIOS.values(), ids=CLIPBOARD_SCENARIOS.keys())
    def test_copy_ocr_result(self, text: str, qapp: QApplication) -> None:
        """Clipboard delivery writes text and reports success."""
        harness = make_workflow(qapp, Config(copy_to=OcrDestination.clipboard))
        harness.workflow.copy_ocr_result(text)
        clipboard = qapp.clipboard()
        assert clipboard is not None
        assert clipboard.text() == text
        harness.notify.notify.assert_called_once_with(f"OCR result copied: {text}")
