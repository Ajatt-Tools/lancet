# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import os
import pathlib
import zipfile

import requests
from loguru import logger
from requests import HTTPError

from lancet.consts import CACHE_DIR_PATH
from lancet.exceptions import LancetHTTPError

# Get from https://github.com/zyddnys/manga-image-translator/releases
DOWNLOAD_URL = "https://github.com/zyddnys/manga-image-translator/releases/download/beta-0.3/comictextdetector.pt"

DOWNLOAD_CHUNK_SIZE: int = 1024
DOWNLOAD_TIMEOUT_SEC: int = 60


def is_valid_checkpoint(file_path: pathlib.Path) -> bool:
    """Return True if the checkpoint file exists and is a valid zip archive (torch checkpoints are zips)."""
    return file_path.is_file() and zipfile.is_zipfile(file_path)


def content_length(response: requests.Response) -> int:
    """Return the expected download size from the Content-Length header, or 0 if absent or unparsable."""
    try:
        return int(response.headers.get("Content-Length", "0"))
    except ValueError:
        return 0


def raise_if_incomplete(partial_path: pathlib.Path, expected_size: int) -> None:
    """Raise LancetHTTPError if the downloaded partial file's size differs from the expected size."""
    actual_size = partial_path.stat().st_size
    if expected_size and actual_size != expected_size:
        raise LancetHTTPError(f"Incomplete download: got {actual_size} of {expected_size} bytes")


class ComicTextDetectorCache:
    """Manages the on-disk cache of the comic text detector model file."""

    def __init__(self) -> None:
        """Set the cache file path and ensure the cache directory exists."""
        self._file_path = CACHE_DIR_PATH / "comictextdetector.pt"
        self._file_path.parent.mkdir(parents=True, exist_ok=True)

    def comic_text_detector_path(self) -> pathlib.Path:
        """Return the path to the model file, downloading it first if missing or corrupt."""
        self._download_if_needed()
        return self._file_path

    def _download_if_needed(self) -> None:
        """Ensure the model file exists and is a valid checkpoint, downloading it otherwise."""
        if is_valid_checkpoint(self._file_path):
            return
        # Drop the corrupt cache file so a truncated download is never reused.
        self._file_path.unlink(missing_ok=True)
        partial_path = self._file_path.with_suffix(".pt.part")
        # Clean up a stale partial from a prior crash before starting a new download.
        partial_path.unlink(missing_ok=True)
        try:
            self._download_to(partial_path)
            if not is_valid_checkpoint(partial_path):
                raise LancetHTTPError(f"Downloaded file is not a valid checkpoint: {DOWNLOAD_URL}")
            os.replace(partial_path, self._file_path)
        finally:
            partial_path.unlink(missing_ok=True)
        logger.info(f"Downloaded {DOWNLOAD_URL}")

    def _download_to(self, partial_path: pathlib.Path) -> None:
        """Stream the model to partial_path, verifying the size against Content-Length."""
        logger.info(f"Downloading {DOWNLOAD_URL}")
        with requests.get(DOWNLOAD_URL, stream=True, verify=True, timeout=DOWNLOAD_TIMEOUT_SEC) as r:
            try:
                r.raise_for_status()
            except HTTPError as ex:
                raise LancetHTTPError(f"Failed to download {DOWNLOAD_URL}: {ex}") from ex
            with partial_path.open("wb") as f:
                for chunk in r.iter_content(DOWNLOAD_CHUNK_SIZE):
                    if chunk:
                        f.write(chunk)
            raise_if_incomplete(partial_path, content_length(r))


def main() -> None:
    cache = ComicTextDetectorCache()
    print(f"path: {cache.comic_text_detector_path()}")


if __name__ == "__main__":
    main()
