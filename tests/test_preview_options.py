# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Tests for screenshot-preview option composition."""

import typing
from collections.abc import Sequence

import pytest

from lancet.config import Config
from lancet.gui.preview_options import make_preview_opts


class PreviewOptsScenario(typing.NamedTuple):
    """Configuration fields and expected screenshot-preview values."""

    border_thickness: int
    border_color: str
    fill_color: str
    outline_color: str
    fill_brush_color: str
    show_help_bar: bool
    expected_alpha_red_green_blue: Sequence[int]


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


def config_from_preview_scenario(scenario: PreviewOptsScenario) -> Config:
    """Build Config from one preview-option scenario."""
    return Config(
        border_thickness=scenario.border_thickness,
        border_color=scenario.border_color,
        fill_color=scenario.fill_color,
        outline_color=scenario.outline_color,
        fill_brush_color=scenario.fill_brush_color,
        show_help_bar=scenario.show_help_bar,
    )


class TestMakePreviewOpts:
    """Test Config-to-preview option composition."""

    @pytest.mark.parametrize("scenario", PREVIEW_OPTS_SCENARIOS.values(), ids=PREVIEW_OPTS_SCENARIOS.keys())
    def test_scalar_fields_round_trip(self, scenario: PreviewOptsScenario) -> None:
        """Scalar preview fields propagate from Config."""
        opts = make_preview_opts(config_from_preview_scenario(scenario))
        assert opts.border_thickness == scenario.border_thickness
        assert opts.show_help is scenario.show_help_bar

    @pytest.mark.parametrize("scenario", PREVIEW_OPTS_SCENARIOS.values(), ids=PREVIEW_OPTS_SCENARIOS.keys())
    def test_border_color_components(self, scenario: PreviewOptsScenario) -> None:
        """The border color parses to the expected ARGB components."""
        opts = make_preview_opts(config_from_preview_scenario(scenario))
        alpha, red, green, blue = scenario.expected_alpha_red_green_blue
        assert (
            opts.border_color.alpha(),
            opts.border_color.red(),
            opts.border_color.green(),
            opts.border_color.blue(),
        ) == (
            alpha,
            red,
            green,
            blue,
        )
