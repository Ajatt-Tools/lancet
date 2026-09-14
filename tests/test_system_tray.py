# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Tests for system-tray helpers, dependency wiring, and menu actions."""

import concurrent.futures
import dataclasses
import pathlib
import signal
import typing
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from contextlib import ExitStack
from unittest.mock import Mock, create_autospec, patch

import pytest
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication
from zala.screenshot import ZalaScreenshot
from zala.take_region import ZalaTakeScreenRegion

from lancet.actions import LancetAction
from lancet.config import Config, make_preview_opts
from lancet.consts import (
    ANKI_SCREENSHOT_ICON_PATH,
    APP_NAME,
    DETECT_AND_OCR_ICON_PATH,
    OCR_ICON_PATH,
    SCREENSHOT_ICON_PATH,
)
from lancet.gui.open_dialogs import OpenDialogs
from lancet.keyboard_shortcuts.listener import LancetShortcutManager
from lancet.model_utils.model_loader import BackgroundModelLoader
from lancet.model_utils.ocr_service import OcrService
from lancet.notifications import NotifySend
from lancet.ocr_history import OcrHistory
from lancet.system_tray import (
    LancetSystemTray,
    format_hotkey,
    make_output_file_path,
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


class ActionIconScenario(typing.NamedTuple):
    """A dedicated action icon and the generic icon it must not reuse."""

    icon_path: pathlib.Path
    generic_icon_path: pathlib.Path


ACTION_ICON_SCENARIOS: dict[str, ActionIconScenario] = {
    "screenshot_to_anki": ActionIconScenario(
        icon_path=ANKI_SCREENSHOT_ICON_PATH,
        generic_icon_path=SCREENSHOT_ICON_PATH,
    ),
    "detect_and_ocr": ActionIconScenario(
        icon_path=DETECT_AND_OCR_ICON_PATH,
        generic_icon_path=OCR_ICON_PATH,
    ),
}


class SvgIconScenario(typing.NamedTuple):
    """An action SVG whose canvas must load and render through Qt."""

    icon_path: pathlib.Path


SVG_ICON_SCENARIOS: dict[str, SvgIconScenario] = {
    "ocr": SvgIconScenario(icon_path=OCR_ICON_PATH),
    "detect_and_ocr": SvgIconScenario(icon_path=DETECT_AND_OCR_ICON_PATH),
    "screenshot_to_anki": SvgIconScenario(icon_path=ANKI_SCREENSHOT_ICON_PATH),
}
SCAN_CORNER_IDS: typing.Final[frozenset[str]] = frozenset(
    {"scan-top-left", "scan-top-right", "scan-bottom-left", "scan-bottom-right"}
)


class SharedCornersScenario(typing.NamedTuple):
    """An action SVG and the scan-frame corners it shares with OCR."""

    icon_path: pathlib.Path
    expected_corner_ids: frozenset[str]


SHARED_CORNERS_SCENARIOS: dict[str, SharedCornersScenario] = {
    "ocr": SharedCornersScenario(icon_path=OCR_ICON_PATH, expected_corner_ids=SCAN_CORNER_IDS),
    "detect_and_ocr": SharedCornersScenario(
        icon_path=DETECT_AND_OCR_ICON_PATH,
        expected_corner_ids=SCAN_CORNER_IDS,
    ),
    "screenshot_to_anki": SharedCornersScenario(
        icon_path=ANKI_SCREENSHOT_ICON_PATH,
        expected_corner_ids=SCAN_CORNER_IDS - {"scan-bottom-right"},
    ),
}


class AnkiStarScenario(typing.NamedTuple):
    """The Anki action SVG that replaces a scan corner with its star mark."""

    icon_path: pathlib.Path


ANKI_STAR_SCENARIOS: dict[str, AnkiStarScenario] = {
    "screenshot_to_anki": AnkiStarScenario(icon_path=ANKI_SCREENSHOT_ICON_PATH),
}


def svg_root(icon_path: pathlib.Path) -> ET.Element:
    """Parse and return one SVG document root."""
    return ET.parse(icon_path).getroot()


def scan_corner_attributes(icon_path: pathlib.Path) -> dict[str, dict[str, str]]:
    """Return scan-frame path attributes keyed by their stable SVG IDs."""
    return {
        element_id: dict(element.attrib)
        for element in svg_root(icon_path)
        if (element_id := element.attrib.get("id", "")).startswith("scan-")
    }


class TestDedicatedActionIcons:
    """Test packaged action icons that distinguish related tray operations."""

    @pytest.mark.parametrize("scenario", ACTION_ICON_SCENARIOS.values(), ids=ACTION_ICON_SCENARIOS.keys())
    def test_icon_exists_and_is_distinct(self, scenario: ActionIconScenario) -> None:
        """Each specialized action has an existing resource distinct from its generic action."""
        assert scenario.icon_path.is_file()
        assert scenario.icon_path != scenario.generic_icon_path
        assert scenario.icon_path.read_bytes() != scenario.generic_icon_path.read_bytes()

    @pytest.mark.parametrize("scenario", SVG_ICON_SCENARIOS.values(), ids=SVG_ICON_SCENARIOS.keys())
    def test_svg_geometry_and_qt_loading(self, scenario: SvgIconScenario, qapp: QApplication) -> None:
        """Every action SVG uses the shared canvas and loads through Qt."""
        root = svg_root(scenario.icon_path)
        assert {key: root.attrib[key] for key in ("width", "height", "viewBox")} == {
            "width": "512",
            "height": "512",
            "viewBox": "0 0 512 512",
        }
        assert QIcon(str(scenario.icon_path)).pixmap(32, 32).isNull() is False

    @pytest.mark.parametrize("scenario", SHARED_CORNERS_SCENARIOS.values(), ids=SHARED_CORNERS_SCENARIOS.keys())
    def test_shared_scan_corners(self, scenario: SharedCornersScenario) -> None:
        """Present scan corners match OCR exactly; only Anki omits bottom-right."""
        reference = scan_corner_attributes(OCR_ICON_PATH)
        actual = scan_corner_attributes(scenario.icon_path)
        assert frozenset(actual) == scenario.expected_corner_ids
        assert actual == {corner_id: reference[corner_id] for corner_id in scenario.expected_corner_ids}

    @pytest.mark.parametrize("scenario", ANKI_STAR_SCENARIOS.values(), ids=ANKI_STAR_SCENARIOS.keys())
    def test_anki_uses_star_without_card(self, scenario: AnkiStarScenario) -> None:
        """The Anki action replaces the fourth corner with only the traced star."""
        element_ids = frozenset(element.attrib.get("id", "") for element in svg_root(scenario.icon_path))
        assert {"anki-star", "scan-top-left", "scan-top-right", "scan-bottom-left"} <= element_ids
        assert element_ids.isdisjoint({"card", "card-plus", "scan-bottom-right"})


class TrayTestContext(typing.NamedTuple):
    """A constructed tray with mocks used to verify dependency wiring."""

    tray: LancetSystemTray
    dependencies: "TrayDependencies"
    patches: "TrayPatches"


class TrayDependencies(typing.NamedTuple):
    """Autospecced dependencies injected while constructing a tray."""

    notify: NotifySend
    screenshot: ZalaScreenshot
    take: ZalaTakeScreenRegion
    open_dialogs: OpenDialogs
    dialog_locked: Mock
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
    anki_workflow_type: Mock
    ocr_service_type: Mock
    hotkeys_type: Mock


class TrayBasicPatches(typing.NamedTuple):
    """Basic service constructor mocks installed for a tray test."""

    notify_type: Mock
    screenshot_type: Mock
    take_type: Mock
    open_dialogs_type: Mock
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
    "make_anki_screenshot",
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
    open_dialogs = create_autospec(OpenDialogs, instance=True)
    dialog_locked = Mock(return_value=False)
    open_dialogs.is_locked = dialog_locked
    return TrayDependencies(
        notify=create_autospec(NotifySend, instance=True),
        screenshot=create_autospec(ZalaScreenshot, instance=True),
        take=create_autospec(ZalaTakeScreenRegion, instance=True),
        open_dialogs=open_dialogs,
        dialog_locked=dialog_locked,
        history=create_autospec(OcrHistory, instance=True),
        loader=loader,
        hotkeys=hotkeys,
        ocr_service=create_autospec(OcrService, instance=True),
        executor=create_autospec(concurrent.futures.ThreadPoolExecutor, instance=True),
        load_all=typing.cast(Mock, loader.load_all),
        start_listener=typing.cast(Mock, hotkeys.start_listener),
    )


def enter_autospec_patch(stack: ExitStack, target: str, return_value: object) -> Mock:
    """Enter an autospecced patch returning the supplied dependency."""
    return stack.enter_context(patch(target, autospec=True, return_value=return_value))


def install_basic_tray_patches(stack: ExitStack, dependencies: TrayDependencies) -> TrayBasicPatches:
    """Install basic service constructor patches in an ExitStack."""
    notify_type = enter_autospec_patch(stack, "lancet.system_tray.NotifySend", dependencies.notify)
    screenshot_type = enter_autospec_patch(stack, "lancet.system_tray.ZalaScreenshot", dependencies.screenshot)
    take_type = enter_autospec_patch(stack, "lancet.system_tray.ZalaTakeScreenRegion", dependencies.take)
    open_dialogs_type = enter_autospec_patch(stack, "lancet.system_tray.OpenDialogs", dependencies.open_dialogs)
    history_type = enter_autospec_patch(stack, "lancet.system_tray.OcrHistory", dependencies.history)
    executor_type = enter_autospec_patch(
        stack, "lancet.system_tray.concurrent.futures.ThreadPoolExecutor", dependencies.executor
    )
    return TrayBasicPatches(
        notify_type=notify_type,
        screenshot_type=screenshot_type,
        take_type=take_type,
        open_dialogs_type=open_dialogs_type,
        history_type=history_type,
        executor_type=executor_type,
    )


def install_tray_constructor_patches(stack: ExitStack, dependencies: TrayDependencies) -> TrayConstructorPatches:
    """Install constructor patches in an ExitStack."""
    basic = install_basic_tray_patches(stack, dependencies)
    loader_new = enter_autospec_patch(stack, "lancet.system_tray.BackgroundModelLoader.new", dependencies.loader)
    workflow_type = stack.enter_context(patch("lancet.system_tray.OcrWorkflow", autospec=True))
    anki_workflow_type = stack.enter_context(patch("lancet.system_tray.AnkiWorkflow", autospec=True))
    ocr_service_type = enter_autospec_patch(stack, "lancet.system_tray.OcrService", dependencies.ocr_service)
    hotkeys_type = enter_autospec_patch(stack, "lancet.system_tray.LancetShortcutManager", dependencies.hotkeys)
    return TrayConstructorPatches(
        basic=basic,
        loader_new=loader_new,
        workflow_type=workflow_type,
        anki_workflow_type=anki_workflow_type,
        ocr_service_type=ocr_service_type,
        hotkeys_type=hotkeys_type,
    )


def install_tray_patches(stack: ExitStack, dependencies: TrayDependencies) -> TrayPatches:
    """Install tray constructor and callback patches in an ExitStack."""
    constructors = install_tray_constructor_patches(stack, dependencies)
    signal_handler = stack.enter_context(patch("lancet.system_tray.signal.signal"))
    qconnect = stack.enter_context(patch("lancet.system_tray.qconnect"))
    callbacks = tuple(stack.enter_context(patch.object(LancetSystemTray, name)) for name in TRAY_CALLBACK_NAMES)
    return TrayPatches(
        constructors=constructors,
        qconnect=qconnect,
        signal_handler=signal_handler,
        callbacks=callbacks,
    )


def create_tray_test_context(qapp: QApplication, cfg: Config) -> TrayTestContext:
    """Construct a tray while replacing external services and background workers."""
    dependencies = make_tray_dependencies()
    with ExitStack() as stack:
        patches = install_tray_patches(stack, dependencies)
        tray = LancetSystemTray(qapp, cfg)
    return TrayTestContext(tray=tray, dependencies=dependencies, patches=patches)


class TrayConstructionScenario(typing.NamedTuple):
    """A tray configuration and expected ordered menu labels."""

    screenshot_shortcut: str
    expected_actions: Sequence[str]
    expected_feature_icons: Sequence[pathlib.Path]
    verify_full_wiring: bool


TRAY_CONSTRUCTION_SCENARIOS: dict[str, TrayConstructionScenario] = {
    "configured_screenshot_shortcut": TrayConstructionScenario(
        screenshot_shortcut="Ctrl+S",
        expected_actions=(
            "Screenshot area (Ctrl+S)",
            "Screenshot to Anki (Alt+I)",
            "OCR screenshot (Alt+O)",
            "Detect and OCR (Shift+Alt+O)",
            "",
            "Preferences…",
            "Restart",
            "About…",
            "Exit",
        ),
        expected_feature_icons=(
            SCREENSHOT_ICON_PATH,
            ANKI_SCREENSHOT_ICON_PATH,
            OCR_ICON_PATH,
            DETECT_AND_OCR_ICON_PATH,
        ),
        verify_full_wiring=True,
    ),
    "empty_screenshot_shortcut": TrayConstructionScenario(
        screenshot_shortcut="",
        expected_actions=(
            "Screenshot area",
            "Screenshot to Anki (Alt+I)",
            "OCR screenshot (Alt+O)",
            "Detect and OCR (Shift+Alt+O)",
            "",
            "Preferences…",
            "Restart",
            "About…",
            "Exit",
        ),
        expected_feature_icons=(
            SCREENSHOT_ICON_PATH,
            ANKI_SCREENSHOT_ICON_PATH,
            OCR_ICON_PATH,
            DETECT_AND_OCR_ICON_PATH,
        ),
        verify_full_wiring=False,
    ),
}


def assert_tray_wiring(context: TrayTestContext, cfg: Config, qapp: QApplication) -> None:
    """Assert model, workflow, listener, and shortcut-signal wiring."""
    constructors = context.patches.constructors
    context.dependencies.load_all.assert_called_once_with()
    context.dependencies.start_listener.assert_called_once_with()
    constructors.loader_new.assert_called_once_with(
        cfg=cfg, notify=context.dependencies.notify, executor=context.dependencies.executor
    )
    constructors.hotkeys_type.assert_called_once_with(cfg.get_pynput_shortcuts().hotkeys)
    constructors.ocr_service_type.assert_called_once_with(loader=context.dependencies.loader, cfg=cfg)
    assert_workflow_wiring(context, cfg, qapp)
    context.patches.qconnect.assert_called_once_with(
        context.dependencies.hotkeys.signals.shortcut_activated,
        context.tray.process_received_command,
    )


def assert_workflow_wiring(context: TrayTestContext, cfg: Config, qapp: QApplication) -> None:
    """Assert OcrWorkflow receives every known injected dependency."""
    workflow_type = context.patches.constructors.workflow_type
    workflow_type.assert_called_once_with(
        app=qapp,
        cfg=cfg,
        loader=context.dependencies.loader,
        ocr_service=context.dependencies.ocr_service,
        notify=context.dependencies.notify,
        history=context.dependencies.history,
        executor=context.dependencies.executor,
    )
    context.patches.constructors.anki_workflow_type.assert_called_once_with(
        cfg,
        executor=context.dependencies.executor,
        notify=context.dependencies.notify,
        take=context.dependencies.take,
        open_dialogs=context.dependencies.open_dialogs,
    )


def assert_tray_constructor_dependencies(context: TrayTestContext, cfg: Config, qapp: QApplication) -> None:
    """Assert notification, capture, history, and signal constructor wiring."""
    basic = context.patches.constructors.basic
    basic.notify_type.assert_called_once_with(context.tray, duration_sec=cfg.notification_duration_sec)
    basic.screenshot_type.assert_called_once_with(qapp)
    basic.take_type.assert_called_once_with(scr=context.dependencies.screenshot)
    basic.open_dialogs_type.assert_called_once_with()
    basic.history_type.assert_called_once_with(cfg.max_history_size)
    basic.executor_type.assert_called_once_with()
    context.patches.signal_handler.assert_called_once_with(signal.SIGINT, context.tray._sigint_handler)


def assert_tray_menu(
    context: TrayTestContext,
    expected_actions: Sequence[str],
    expected_feature_icons: Sequence[pathlib.Path],
) -> None:
    """Assert ordered tray actions and separator placement."""
    menu = context.tray.contextMenu()
    assert menu is not None
    assert [action.text() for action in menu.actions()] == list(expected_actions)
    assert menu.actions()[4].isSeparator() is True
    assert [action.icon().pixmap(32, 32).toImage() for action in menu.actions()[:4]] == [
        QIcon(str(icon_path)).pixmap(32, 32).toImage() for icon_path in expected_feature_icons
    ]


def assert_tray_callbacks(context: TrayTestContext) -> None:
    """Trigger every feature/system action and verify its exclusive callback."""
    menu = context.tray.contextMenu()
    assert menu is not None
    actions = [action for action in menu.actions() if not action.isSeparator()]
    for selected_action, selected_callback in zip(actions, context.patches.callbacks, strict=True):
        for callback in context.patches.callbacks:
            callback.reset_mock()
        selected_action.trigger()
        assert selected_callback.call_count == 1
        assert sum(callback.call_count for callback in context.patches.callbacks) == 1


class TestLancetSystemTrayConstruction:
    """Test dependency and menu wiring performed by the tray constructor."""

    @pytest.mark.parametrize("scenario", TRAY_CONSTRUCTION_SCENARIOS.values(), ids=TRAY_CONSTRUCTION_SCENARIOS.keys())
    def test_workflow_and_menu_wiring(self, scenario: TrayConstructionScenario, qapp: QApplication) -> None:
        """The tray wires workflows and eight ordered actions around a separator."""
        cfg = Config(screenshot_shortcut=scenario.screenshot_shortcut)
        context = create_tray_test_context(qapp, cfg)
        with ExitStack() as stack:
            stack.callback(context.tray._executor.shutdown, wait=True)
            assert_tray_menu(context, scenario.expected_actions, scenario.expected_feature_icons)
            if scenario.verify_full_wiring:
                assert_tray_wiring(context, cfg, qapp)
                assert_tray_constructor_dependencies(context, cfg, qapp)
                assert_tray_callbacks(context)


class TrayCommandScenario(typing.NamedTuple):
    """One received action, dialog state, and expected tray callback name."""

    action: LancetAction
    dialog_locked: bool
    expected_callback_name: str | None


TRAY_COMMAND_SCENARIOS: dict[str, TrayCommandScenario] = {
    "ocr": TrayCommandScenario(
        action=LancetAction.ocr,
        dialog_locked=False,
        expected_callback_name="make_ocr_screenshot",
    ),
    "detect_and_ocr": TrayCommandScenario(
        action=LancetAction.detect_and_ocr,
        dialog_locked=False,
        expected_callback_name="detect_and_make_ocr_screenshot",
    ),
    "screenshot": TrayCommandScenario(
        action=LancetAction.screenshot,
        dialog_locked=False,
        expected_callback_name="make_screenshot_area",
    ),
    "screenshot_to_anki": TrayCommandScenario(
        action=LancetAction.screenshot_to_anki,
        dialog_locked=False,
        expected_callback_name="make_anki_screenshot",
    ),
    "dialog_locked": TrayCommandScenario(
        action=LancetAction.screenshot_to_anki,
        dialog_locked=True,
        expected_callback_name=None,
    ),
}


class TestLancetSystemTrayCommandDispatch:
    """Test IPC and shortcut action dispatch through the current tray state."""

    @pytest.mark.parametrize("scenario", TRAY_COMMAND_SCENARIOS.values(), ids=TRAY_COMMAND_SCENARIOS.keys())
    def test_received_command(self, scenario: TrayCommandScenario, qapp: QApplication) -> None:
        """Each action invokes one callback unless a dialog is currently open."""
        context = create_tray_test_context(qapp, Config())
        context.dependencies.dialog_locked.return_value = scenario.dialog_locked
        with ExitStack() as stack:
            stack.callback(context.tray._executor.shutdown, wait=True)
            for name, callback in zip(TRAY_CALLBACK_NAMES, context.patches.callbacks, strict=True):
                stack.enter_context(patch.object(LancetSystemTray, name, callback))
                callback.reset_mock()
            context.tray.process_received_command(scenario.action)
        if scenario.expected_callback_name is None:
            assert sum(callback.call_count for callback in context.patches.callbacks) == 0
            return
        callback_index = TRAY_CALLBACK_NAMES.index(scenario.expected_callback_name)
        assert context.patches.callbacks[callback_index].call_count == 1
        assert sum(callback.call_count for callback in context.patches.callbacks) == 1
