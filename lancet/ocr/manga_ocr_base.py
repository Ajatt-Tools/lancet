# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import abc
import pathlib

from PIL import Image


class MangaOcrBase(abc.ABC):
    @abc.abstractmethod
    def recognize(self, img_or_path: str | pathlib.Path | Image.Image) -> str:
        raise NotImplementedError
