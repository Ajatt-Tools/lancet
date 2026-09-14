# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
import dataclasses
import typing

from lancet.config import Config


@dataclasses.dataclass(frozen=True)
class AnkiConnectSettings:
    """Connection and target-field settings for one Anki attachment operation."""

    url: str
    api_key: str
    field_name: str
    field_separator: str

    @classmethod
    def from_config(cls, cfg: Config) -> typing.Self:
        """Capture an AnkiConnect target from the current application configuration."""
        return cls(
            url=cfg.anki_connect_url,
            api_key=cfg.anki_connect_api_key,
            field_name=cfg.anki_image_field,
            field_separator=cfg.anki_field_separator,
        )
