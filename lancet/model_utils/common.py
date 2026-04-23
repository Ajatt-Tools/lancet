# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html


def class_name(obj: object) -> str:
    """Return the class name of the given object, typically used for exception formatting."""
    return obj.__class__.__name__
