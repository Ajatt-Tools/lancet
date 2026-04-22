# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import pathlib

import requests
from loguru import logger
from requests import HTTPError

from lancet.consts import CACHE_DIR_PATH
from lancet.exceptions import LancetHTTPError

# Get from https://github.com/zyddnys/manga-image-translator/releases
DOWNLOAD_URL = "https://github.com/zyddnys/manga-image-translator/releases/download/beta-0.3/comictextdetector.pt"


class ComicTextDetectorCache:
    def __init__(self):
        self._file_path = CACHE_DIR_PATH / "comictextdetector.pt"
        self._file_path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def comic_text_detector_path(self) -> pathlib.Path:
        self._download_if_needed()
        return self._file_path

    def _download_if_needed(self) -> None:
        if not self._file_path.is_file():
            logger.info(f"Downloading {DOWNLOAD_URL}")
            r = requests.get(DOWNLOAD_URL, stream=True, verify=True)
            try:
                r.raise_for_status()
            except HTTPError as ex:
                raise LancetHTTPError(f"Failed to download {DOWNLOAD_URL}: {ex}")
            with self._file_path.open("wb") as f:
                for chunk in r.iter_content(1024):
                    if chunk:
                        f.write(chunk)
            logger.info(f"Downloaded {DOWNLOAD_URL}")


def main() -> None:
    cache = ComicTextDetectorCache()
    print(f"path: {cache.comic_text_detector_path}")


if __name__ == "__main__":
    main()
