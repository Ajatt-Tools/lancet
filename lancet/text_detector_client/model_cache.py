# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import os
import pathlib
import zipfile

import requests
from loguru import logger

from lancet.consts import CACHE_DIR_PATH
from lancet.exceptions import LancetHTTPError

# Get from https://github.com/zyddnys/manga-image-translator/releases
DOWNLOAD_URL = "https://github.com/zyddnys/manga-image-translator/releases/download/beta-0.3/comictextdetector.pt"

DOWNLOAD_CHUNK_SIZE: int = 1024
DOWNLOAD_TIMEOUT_SEC: int = 60
EXPECTED_CHECKPOINT_SIZE_BYTES: int = 79_948_869


def is_valid_checkpoint(file_path: pathlib.Path) -> bool:
    """Return True if the checkpoint is a regular ZIP file with the pinned asset size."""
    try:
        return (
            file_path.is_file()
            and file_path.stat().st_size == EXPECTED_CHECKPOINT_SIZE_BYTES
            and zipfile.is_zipfile(file_path)
        )
    except OSError:
        return False


def content_length(response: requests.Response) -> int:
    """Return the expected download size from the Content-Length header, or 0 if absent or unparsable."""
    try:
        return int(response.headers.get("Content-Length", "0"))
    except ValueError:
        return 0


def raise_if_incomplete(partial_path: pathlib.Path, expected_size: int) -> None:
    """Raise LancetHTTPError when a partial file differs from HTTP or pinned checkpoint sizes."""
    actual_size = partial_path.stat().st_size
    if expected_size and actual_size != expected_size:
        raise LancetHTTPError(f"Incomplete download: got {actual_size} of {expected_size} bytes")
    if actual_size != EXPECTED_CHECKPOINT_SIZE_BYTES:
        raise LancetHTTPError(
            f"Unexpected checkpoint size: got {actual_size} of {EXPECTED_CHECKPOINT_SIZE_BYTES} bytes"
        )


def download_comic_text_detector_pt(destination_path: pathlib.Path) -> None:
    """Stream the model to destination_path, verifying its HTTP and pinned release sizes."""
    logger.info(f"Downloading {DOWNLOAD_URL}")
    try:
        with requests.get(DOWNLOAD_URL, stream=True, verify=True, timeout=DOWNLOAD_TIMEOUT_SEC) as r:
            r.raise_for_status()
            with destination_path.open("wb") as f:
                for chunk in r.iter_content(DOWNLOAD_CHUNK_SIZE):
                    if chunk:
                        f.write(chunk)
            raise_if_incomplete(destination_path, content_length(r))
    except requests.RequestException as ex:
        raise LancetHTTPError(f"Failed to download {DOWNLOAD_URL}: {ex}") from ex


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
            download_comic_text_detector_pt(partial_path)
            if not is_valid_checkpoint(partial_path):
                raise LancetHTTPError(f"Downloaded file is not a valid checkpoint: {DOWNLOAD_URL}")
            os.replace(partial_path, self._file_path)
        finally:
            partial_path.unlink(missing_ok=True)
        logger.info(f"Downloaded {DOWNLOAD_URL}")


def main() -> None:
    """Download the text detector checkpoint if needed and print its cached path."""
    cache = ComicTextDetectorCache()
    print(f"path: {cache.comic_text_detector_path()}")


if __name__ == "__main__":
    main()
