# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""Exceptions specific to preference-widget value conversion."""

from PyQt6.QtWidgets import QWidget

from lancet.config import CfgValueTypes


class WidgetSetValueError(ValueError):
    """Raised when a configuration value cannot populate a specific widget type."""

    def __init__(self, widget: QWidget, value: CfgValueTypes) -> None:
        """Describe the incompatible widget and configuration value types."""
        super().__init__(
            f"Can't handle widget of type {type(widget).__name__} and value of type {type(value).__name__}"
        )
