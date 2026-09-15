# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Construct visual screenshot-selection options from application configuration."""

from PyQt6.QtGui import QColor
from zala.config import ScreenshotPreviewOpts

from lancet.config import Config


def make_preview_opts(cfg: Config) -> ScreenshotPreviewOpts:
    """Build screenshot overlay options from the current configuration."""
    return ScreenshotPreviewOpts(
        border_thickness=cfg.border_thickness,
        border_color=QColor.fromString(cfg.border_color),
        fill_color=QColor.fromString(cfg.fill_color),
        outline_color=QColor.fromString(cfg.outline_color),
        fill_brush_color=QColor.fromString(cfg.fill_brush_color),
        show_help=cfg.show_help_bar,
    )
