# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Tests for system-tray helpers, dependency wiring, and menu actions."""

import concurrent.futures
import dataclasses
import pathlib
import signal
import typing
from collections.abc import Sequence
from contextlib import ExitStack
from unittest.mock import Mock, create_autospec, patch

import pytest
from PyQt6.QtWidgets import QApplication
from zala.screenshot import ZalaScreenshot
from zala.take_region import ZalaTakeScreenRegion

from lancet.config import Config
from lancet.consts import APP_NAME
from lancet.keyboard_shortcuts.listener import LancetShortcutManager
from lancet.model_utils.model_loader import BackgroundModelLoader
from lancet.model_utils.ocr_service import OcrService
from lancet.notifications import NotifySend
from lancet.ocr_history import OcrHistory
from lancet.system_tray import (
    LancetSystemTray,
    format_hotkey,
    make_output_file_path,
    make_preview_opts,
)


@dataclasses.dataclass
class PreviewOptsScenario:
    """A Config subset and expected screenshot-preview values."""

    border_thickness: int
    border_color: str
    fill_color: str
    outline_color: str
    fill_brush_color: str
    show_help_bar: bool
    expected_alpha_red_green_blue: tuple[int, int, int, int]


PREVIEW_OPTS_SCENARIOS: dict[str, PreviewOptsScenario] = {
    "config_defaults": PreviewOptsScenario(
        border_thickness=2,
        border_color="#7F0000FF",
        fill_color="#3C0080FF",
        outline_color="#7FFF0000",
        fill_brush_color="#557F7F7F",
        show_help_bar=True,
        expected_alpha_red_green_blue=(127, 0, 0, 255),
    ),
    "thicker_border_help_off": PreviewOptsScenario(
        border_thickness=8,
        border_color="#FF112233",
        fill_color="#80445566",
        outline_color="#A0AABBCC",
        fill_brush_color="#10112233",
        show_help_bar=False,
        expected_alpha_red_green_blue=(255, 17, 34, 51),
    ),
}


def build_cfg_from_preview_scenario(scenario: PreviewOptsScenario) -> Config:
    """Create a Config carrying the scenario's preview-related fields."""
    d = dataclasses.asdict(scenario)
    del d["expected_alpha_red_green_blue"]
    return Config(**d)


class TestMakePreviewOpts:
    """make_preview_opts mirrors Config overlay fields."""

    @pytest.mark.parametrize("scenario", PREVIEW_OPTS_SCENARIOS.values(), ids=PREVIEW_OPTS_SCENARIOS.keys())
    def test_scalar_fields_round_trip(self, scenario: PreviewOptsScenario) -> None:
        """Scalar preview fields propagate from Config."""
        opts = make_preview_opts(build_cfg_from_preview_scenario(scenario))
        assert opts.border_thickness == scenario.border_thickness
        assert opts.show_help is scenario.show_help_bar

    @pytest.mark.parametrize("scenario", PREVIEW_OPTS_SCENARIOS.values(), ids=PREVIEW_OPTS_SCENARIOS.keys())
    def test_border_color_components(self, scenario: PreviewOptsScenario) -> None:
        """The border color parses to the expected ARGB components."""
        opts = make_preview_opts(build_cfg_from_preview_scenario(scenario))
        alpha, red, green, blue = scenario.expected_alpha_red_green_blue
        assert opts.border_color.alpha() == alpha
        assert opts.border_color.red() == red
        assert opts.border_color.green() == green
        assert opts.border_color.blue() == blue


class FormatHotkeyScenario(typing.NamedTuple):
    """A menu label, shortcut, and expected decorated label."""

    menu_label: str
    keyboard_shortcut: str
    expected: str


FORMAT_HOTKEY_SCENARIOS: dict[str, FormatHotkeyScenario] = {
    "non_empty_shortcut_appended": FormatHotkeyScenario("OCR screenshot", "Alt+O", "OCR screenshot (Alt+O)"),
    "empty_shortcut_returns_label": FormatHotkeyScenario("OCR screenshot", "", "OCR screenshot"),
    "complex_shortcut_appended": FormatHotkeyScenario(
        "Detect and OCR", "Ctrl+Shift+F12", "Detect and OCR (Ctrl+Shift+F12)"
    ),
}


class TestFormatHotkey:
    """format_hotkey decorates menu labels only when a shortcut exists."""

    @pytest.mark.parametrize("scenario", FORMAT_HOTKEY_SCENARIOS.values(), ids=FORMAT_HOTKEY_SCENARIOS.keys())
    def test_format(self, scenario: FormatHotkeyScenario) -> None:
        """Each scenario produces its expected menu label."""
        assert format_hotkey(scenario.menu_label, scenario.keyboard_shortcut) == scenario.expected


class TestMakeOutputFilePath:
    """make_output_file_path creates timestamped screenshot paths."""

    @pytest.mark.parametrize(
        "attribute,expected",
        [
            ("parent", pathlib.Path.home() / "Pictures" / "Screenshots"),
            ("suffix", ".png"),
        ],
        ids=("pictures_directory", "png_suffix"),
    )
    def test_path_attribute(self, attribute: str, expected: pathlib.Path | str) -> None:
        """Static path attributes match the screenshot storage convention."""
        assert getattr(make_output_file_path(), attribute) == expected

    @pytest.mark.parametrize("prefix", (APP_NAME,))
    def test_path_name_contains_app_name(self, prefix: str) -> None:
        """The basename starts with the application name."""
        assert make_output_file_path().name.startswith(prefix)


class TrayHarness(typing.NamedTuple):
    """A constructed tray and mocks used to verify dependency wiring."""

    tray: LancetSystemTray
    dependencies: "TrayDependencies"
    patches: "TrayPatches"


class TrayDependencies(typing.NamedTuple):
    """Autospecced dependencies injected while constructing a tray."""

    notify: NotifySend
    screenshot: ZalaScreenshot
    take: ZalaTakeScreenRegion
    history: OcrHistory
    loader: BackgroundModelLoader
    hotkeys: LancetShortcutManager
    ocr_service: OcrService
    executor: concurrent.futures.ThreadPoolExecutor
    load_all: Mock
    start_listener: Mock


class TrayConstructorPatches(typing.NamedTuple):
    """Constructor mocks installed for a tray test."""

    basic: "TrayBasicPatches"
    loader_new: Mock
    workflow_type: Mock
    ocr_service_type: Mock
    hotkeys_type: Mock


class TrayBasicPatches(typing.NamedTuple):
    """Basic service constructor mocks installed for a tray test."""

    notify_type: Mock
    screenshot_type: Mock
    take_type: Mock
    history_type: Mock
    executor_type: Mock


class TrayPatches(typing.NamedTuple):
    """Grouped constructor, signal, and callback patches for a tray test."""

    constructors: TrayConstructorPatches
    qconnect: Mock
    signal_handler: Mock
    callbacks: Sequence[Mock]


TRAY_CALLBACK_NAMES: typing.Final[Sequence[str]] = (
    "make_screenshot_area",
    "make_ocr_screenshot",
    "detect_and_make_ocr_screenshot",
    "open_preferences",
    "restart",
    "open_about",
    "quit",
)


def make_shortcut_manager_mock() -> LancetShortcutManager:
    """Create a shortcut-manager double with its runtime-owned signal namespace."""
    hotkeys = create_autospec(LancetShortcutManager, instance=True)
    hotkeys.signals = Mock()
    hotkeys.signals.shortcut_activated = Mock()
    return hotkeys


def make_tray_dependencies() -> TrayDependencies:
    """Create autospecced tray dependencies."""
    loader = create_autospec(BackgroundModelLoader, instance=True)
    hotkeys = make_shortcut_manager_mock()
    return TrayDependencies(
        create_autospec(NotifySend, instance=True),
        create_autospec(ZalaScreenshot, instance=True),
        create_autospec(ZalaTakeScreenRegion, instance=True),
        create_autospec(OcrHistory, instance=True),
        loader,
        hotkeys,
        create_autospec(OcrService, instance=True),
        create_autospec(concurrent.futures.ThreadPoolExecutor, instance=True),
        typing.cast(Mock, loader.load_all),
        typing.cast(Mock, hotkeys.start_listener),
    )


def enter_autospec_patch(stack: ExitStack, target: str, return_value: object) -> Mock:
    """Enter an autospecced patch returning the supplied dependency."""
    return stack.enter_context(patch(target, autospec=True, return_value=return_value))


def install_basic_tray_patches(stack: ExitStack, dependencies: TrayDependencies) -> TrayBasicPatches:
    """Install basic service constructor patches in an ExitStack."""
    notify_type = enter_autospec_patch(stack, "lancet.system_tray.NotifySend", dependencies.notify)
    screenshot_type = enter_autospec_patch(stack, "lancet.system_tray.ZalaScreenshot", dependencies.screenshot)
    take_type = enter_autospec_patch(stack, "lancet.system_tray.ZalaTakeScreenRegion", dependencies.take)
    history_type = enter_autospec_patch(stack, "lancet.system_tray.OcrHistory", dependencies.history)
    executor_type = enter_autospec_patch(
        stack, "lancet.system_tray.concurrent.futures.ThreadPoolExecutor", dependencies.executor
    )
    return TrayBasicPatches(notify_type, screenshot_type, take_type, history_type, executor_type)


def install_tray_constructor_patches(stack: ExitStack, dependencies: TrayDependencies) -> TrayConstructorPatches:
    """Install constructor patches in an ExitStack."""
    basic = install_basic_tray_patches(stack, dependencies)
    loader_new = enter_autospec_patch(stack, "lancet.system_tray.BackgroundModelLoader.new", dependencies.loader)
    workflow_type = stack.enter_context(patch("lancet.system_tray.OcrWorkflow", autospec=True))
    ocr_service_type = enter_autospec_patch(stack, "lancet.system_tray.OcrService", dependencies.ocr_service)
    hotkeys_type = enter_autospec_patch(stack, "lancet.system_tray.LancetShortcutManager", dependencies.hotkeys)
    return TrayConstructorPatches(basic, loader_new, workflow_type, ocr_service_type, hotkeys_type)


def install_tray_patches(stack: ExitStack, dependencies: TrayDependencies) -> TrayPatches:
    """Install tray constructor and callback patches in an ExitStack."""
    constructors = install_tray_constructor_patches(stack, dependencies)
    signal_handler = stack.enter_context(patch("lancet.system_tray.signal.signal"))
    qconnect = stack.enter_context(patch("lancet.system_tray.qconnect"))
    callbacks = tuple(stack.enter_context(patch.object(LancetSystemTray, name)) for name in TRAY_CALLBACK_NAMES)
    return TrayPatches(constructors, qconnect, signal_handler, callbacks)


def make_tray_harness(qapp: QApplication, cfg: Config) -> TrayHarness:
    """Construct a tray while replacing external services and background workers."""
    dependencies = make_tray_dependencies()
    with ExitStack() as stack:
        patches = install_tray_patches(stack, dependencies)
        tray = LancetSystemTray(qapp, cfg)
    return TrayHarness(tray, dependencies, patches)


class TrayConstructionScenario(typing.NamedTuple):
    """A tray configuration and expected ordered menu labels."""

    screenshot_shortcut: str
    expected_actions: Sequence[str]
    verify_full_wiring: bool


TRAY_CONSTRUCTION_SCENARIOS: dict[str, TrayConstructionScenario] = {
    "configured_screenshot_shortcut": TrayConstructionScenario(
        "Ctrl+S",
        (
            "Screenshot area (Ctrl+S)",
            "OCR screenshot (Alt+O)",
            "Detect and OCR (Shift+Alt+O)",
            "",
            "Preferences…",
            "Restart",
            "About…",
            "Exit",
        ),
        True,
    ),
    "empty_screenshot_shortcut": TrayConstructionScenario(
        "",
        (
            "Screenshot area",
            "OCR screenshot (Alt+O)",
            "Detect and OCR (Shift+Alt+O)",
            "",
            "Preferences…",
            "Restart",
            "About…",
            "Exit",
        ),
        False,
    ),
}


def assert_tray_wiring(harness: TrayHarness, cfg: Config, qapp: QApplication) -> None:
    """Assert model, workflow, listener, and shortcut-signal wiring."""
    constructors = harness.patches.constructors
    harness.dependencies.load_all.assert_called_once_with()
    harness.dependencies.start_listener.assert_called_once_with()
    constructors.loader_new.assert_called_once_with(
        cfg=cfg, notify=harness.dependencies.notify, executor=harness.dependencies.executor
    )
    constructors.hotkeys_type.assert_called_once_with(cfg.get_pynput_shortcuts().hotkeys)
    constructors.ocr_service_type.assert_called_once_with(loader=harness.dependencies.loader, cfg=cfg)
    assert_workflow_wiring(harness, cfg, qapp)
    harness.patches.qconnect.assert_called_once_with(
        harness.dependencies.hotkeys.signals.shortcut_activated,
        harness.tray.process_received_command,
    )


def assert_workflow_wiring(harness: TrayHarness, cfg: Config, qapp: QApplication) -> None:
    """Assert OcrWorkflow receives every known injected dependency."""
    workflow_type = harness.patches.constructors.workflow_type
    workflow_type.assert_called_once_with(
        app=qapp,
        cfg=cfg,
        loader=harness.dependencies.loader,
        ocr_service=harness.dependencies.ocr_service,
        notify=harness.dependencies.notify,
        history=harness.dependencies.history,
        executor=harness.dependencies.executor,
    )


def assert_tray_constructor_dependencies(harness: TrayHarness, cfg: Config, qapp: QApplication) -> None:
    """Assert notification, capture, history, and signal constructor wiring."""
    basic = harness.patches.constructors.basic
    basic.notify_type.assert_called_once_with(harness.tray, duration_sec=cfg.notification_duration_sec)
    basic.screenshot_type.assert_called_once_with(qapp)
    basic.take_type.assert_called_once_with(scr=harness.dependencies.screenshot)
    basic.history_type.assert_called_once_with(cfg.max_history_size)
    basic.executor_type.assert_called_once_with()
    harness.patches.signal_handler.assert_called_once_with(signal.SIGINT, harness.tray._sigint_handler)


def assert_tray_menu(harness: TrayHarness, expected_actions: Sequence[str]) -> None:
    """Assert ordered tray actions and separator placement."""
    menu = harness.tray.contextMenu()
    assert menu is not None
    assert [action.text() for action in menu.actions()] == list(expected_actions)
    assert menu.actions()[3].isSeparator() is True


def assert_tray_callbacks(harness: TrayHarness) -> None:
    """Trigger every feature/system action and verify its exclusive callback."""
    menu = harness.tray.contextMenu()
    assert menu is not None
    actions = [action for action in menu.actions() if not action.isSeparator()]
    for selected_action, selected_callback in zip(actions, harness.patches.callbacks, strict=True):
        for callback in harness.patches.callbacks:
            callback.reset_mock()
        selected_action.trigger()
        assert selected_callback.call_count == 1
        assert sum(callback.call_count for callback in harness.patches.callbacks) == 1


class TestLancetSystemTrayConstruction:
    """Test dependency and menu wiring performed by the tray constructor."""

    @pytest.mark.parametrize("scenario", TRAY_CONSTRUCTION_SCENARIOS.values(), ids=TRAY_CONSTRUCTION_SCENARIOS.keys())
    def test_workflow_and_menu_wiring(self, scenario: TrayConstructionScenario, qapp: QApplication) -> None:
        """The tray wires one OCR workflow and seven ordered actions around a separator."""
        cfg = Config(screenshot_shortcut=scenario.screenshot_shortcut)
        harness = make_tray_harness(qapp, cfg)
        with ExitStack() as stack:
            stack.callback(harness.tray._executor.shutdown, wait=True)
            assert_tray_menu(harness, scenario.expected_actions)
            if scenario.verify_full_wiring:
                assert_tray_wiring(harness, cfg, qapp)
                assert_tray_constructor_dependencies(harness, cfg, qapp)
                assert_tray_callbacks(harness)
