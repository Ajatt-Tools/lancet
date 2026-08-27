# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import io
import pathlib
import re
import typing
import zipfile
from collections.abc import Iterator
from unittest.mock import Mock

import pytest
import requests

from lancet.exceptions import LancetHTTPError
from lancet.text_detector_client.model_cache import (
    DOWNLOAD_TIMEOUT_SEC,
    DOWNLOAD_URL,
    ComicTextDetectorCache,
    content_length,
    is_valid_checkpoint,
    raise_if_incomplete,
)

MODEL_FILE_NAME = "comictextdetector.pt"
FAILED_DOWNLOAD_RE = re.compile("Failed to download")
UNEXPECTED_CHECKPOINT_SIZE_RE = re.compile("Unexpected checkpoint size")


def make_checkpoint_bytes(payload_size: int = 4096) -> bytes:
    """Build a small valid ZIP checkpoint payload with a deterministic size."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("weights.bin", b"x" * payload_size)
    return buffer.getvalue()


@pytest.fixture(autouse=True)
def expected_checkpoint_size(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reduce the pinned checkpoint size so download tests use small fixture payloads."""
    monkeypatch.setattr(
        "lancet.text_detector_client.model_cache.EXPECTED_CHECKPOINT_SIZE_BYTES",
        len(make_checkpoint_bytes()),
    )


class FakeResponse(requests.Response):
    """A requests.Response stand-in for the download code path (subclasses Response to satisfy beartype)."""

    def __init__(
        self,
        body: bytes,
        *,
        http_ok: bool = True,
        fail_at_chunk: int | None = None,
        size_delta: int = 0,
        include_content_length: bool = True,
        content_length_value: str | None = None,
    ) -> None:
        """Store the body and configure status, Content-Length header, and optional mid-stream failure."""
        super().__init__()
        self.status_code = 200 if http_ok else 404
        if include_content_length:
            self.headers["Content-Length"] = (
                content_length_value if content_length_value is not None else str(len(body) + size_delta)
            )
        self._body = body
        self._fail_at_chunk = fail_at_chunk
        # Response.close() (called from the "with" block) touches self.raw; give it a real stream.
        self.raw = io.BytesIO(body)

    def iter_content(self, chunk_size: int | None = 1, decode_unicode: bool = False) -> Iterator[bytes]:
        """Yield the body in chunks, optionally raising ChunkedEncodingError at a given chunk index."""
        for index, offset in enumerate(range(0, len(self._body), chunk_size or 1)):
            if self._fail_at_chunk is not None and index == self._fail_at_chunk:
                raise requests.exceptions.ChunkedEncodingError("connection dropped")
            yield self._body[offset : offset + (chunk_size or 1)]


def install_fake_get(
    monkeypatch: pytest.MonkeyPatch,
    body: bytes,
    *,
    http_ok: bool = True,
    fail_at_chunk: int | None = None,
    size_delta: int = 0,
    include_content_length: bool = True,
    content_length_value: str | None = None,
) -> Mock:
    """Patch requests.get in the model_cache module to return a FakeResponse."""
    fake_get = Mock(
        return_value=FakeResponse(
            body,
            http_ok=http_ok,
            fail_at_chunk=fail_at_chunk,
            size_delta=size_delta,
            include_content_length=include_content_length,
            content_length_value=content_length_value,
        )
    )
    monkeypatch.setattr(
        "lancet.text_detector_client.model_cache.requests.get",
        fake_get,
    )
    return fake_get


def install_cache_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> pathlib.Path:
    """Point the model_cache module's CACHE_DIR_PATH at a temporary directory and return the model file path."""
    monkeypatch.setattr("lancet.text_detector_client.model_cache.CACHE_DIR_PATH", tmp_path)
    return tmp_path / MODEL_FILE_NAME


class TestIsValidCheckpoint:
    """Test is_valid_checkpoint with various file states."""

    @pytest.mark.parametrize(
        "content_kind,write_file,expected",
        [
            ("valid_zip", True, True),
            ("exact_size_non_zip", True, False),
            ("wrong_size", True, False),
            ("empty_file", True, False),
            ("missing_file", False, False),
        ],
        ids=["valid_zip", "exact_size_non_zip", "wrong_size", "empty_file", "missing_file"],
    )
    def test_validate(self, content_kind: str, write_file: bool, expected: bool, tmp_path: pathlib.Path) -> None:
        """A file is valid only if it is a regular ZIP file with the pinned checkpoint size."""
        file_path = tmp_path / "checkpoint.pt"
        if write_file:
            checkpoint = make_checkpoint_bytes()
            content = {
                "valid_zip": checkpoint,
                "exact_size_non_zip": b"x" * len(checkpoint),
                "wrong_size": b"not a zip at all",
                "empty_file": b"",
            }[content_kind]
            file_path.write_bytes(content)
        assert is_valid_checkpoint(file_path) == expected


class CacheStateScenario(typing.NamedTuple):
    """Initial cache files and whether a fresh download is expected."""

    model_contents: bytes | None
    stale_partial: bool
    expect_download: bool


CACHE_STATE_SCENARIOS: dict[str, CacheStateScenario] = {
    "missing_model_downloads": CacheStateScenario(None, False, True),
    "valid_model_skips_download": CacheStateScenario(make_checkpoint_bytes(), False, False),
    "corrupt_model_redownloads": CacheStateScenario(b"truncated garbage", False, True),
    "stale_partial_is_replaced": CacheStateScenario(None, True, True),
}


class CacheStateHarness(typing.NamedTuple):
    """Prepared cache paths, response body, and network mock."""

    model_path: pathlib.Path
    partial_path: pathlib.Path
    body: bytes
    fake_get: Mock


def prepare_cache_state(
    scenario: CacheStateScenario, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> CacheStateHarness:
    """Create one initial cache state and configure its network behavior."""
    model_path = install_cache_dir(monkeypatch, tmp_path)
    partial_path = model_path.with_suffix(".pt.part")
    if scenario.model_contents is not None:
        model_path.write_bytes(scenario.model_contents)
    if scenario.stale_partial:
        partial_path.write_bytes(b"stale partial")
    body = make_checkpoint_bytes()
    fake_get = install_fake_get(monkeypatch, body) if scenario.expect_download else Mock()
    if not scenario.expect_download:
        fake_get.side_effect = AssertionError("requests.get must not be called")
        monkeypatch.setattr("lancet.text_detector_client.model_cache.requests.get", fake_get)
    return CacheStateHarness(model_path, partial_path, body, fake_get)


def assert_cache_state(scenario: CacheStateScenario, harness: CacheStateHarness) -> None:
    """Assert final cache bytes, partial cleanup, and network behavior."""
    expected_contents = harness.body if scenario.expect_download else scenario.model_contents
    assert harness.model_path.read_bytes() == expected_contents
    assert harness.partial_path.exists() is False
    assert harness.fake_get.call_count == int(scenario.expect_download)
    if scenario.expect_download:
        assert harness.fake_get.call_args.args == (DOWNLOAD_URL,)
        assert harness.fake_get.call_args.kwargs == {
            "stream": True,
            "verify": True,
            "timeout": DOWNLOAD_TIMEOUT_SEC,
        }


class TestComicTextDetectorCache:
    """Test ComicTextDetectorCache download, validation, and self-healing behavior."""

    @pytest.mark.parametrize("scenario", CACHE_STATE_SCENARIOS.values(), ids=CACHE_STATE_SCENARIOS.keys())
    def test_cache_state(
        self, scenario: CacheStateScenario, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
    ) -> None:
        """Use valid caches and replace missing, corrupt, or partial checkpoints."""
        harness = prepare_cache_state(scenario, monkeypatch, tmp_path)
        result = ComicTextDetectorCache().comic_text_detector_path()
        assert result == harness.model_path
        assert_cache_state(scenario, harness)


class DownloadFailureScenario(typing.NamedTuple):
    """A scenario describing a failed download attempt and its expected outcome."""

    body: bytes  # bytes served by the fake server
    http_ok: bool  # if False, raise_for_status raises HTTPError
    fail_at_chunk: int | None  # if set, iter_content raises ChunkedEncodingError at this chunk index
    size_delta: int  # added to the real Content-Length to simulate a size mismatch
    expected_error: type[Exception]  # exception type expected to propagate
    expected_message: str  # substring expected in the exception message; empty means no check


DOWNLOAD_FAILURE_SCENARIOS: dict[str, DownloadFailureScenario] = {
    "http_error": DownloadFailureScenario(
        body=b"",
        http_ok=False,
        fail_at_chunk=None,
        size_delta=0,
        expected_error=LancetHTTPError,
        expected_message="Failed to download",
    ),
    "connection_dropped_mid_stream": DownloadFailureScenario(
        body=make_checkpoint_bytes(),
        http_ok=True,
        fail_at_chunk=1,
        size_delta=0,
        expected_error=LancetHTTPError,
        expected_message="Failed to download",
    ),
    "incomplete_download": DownloadFailureScenario(
        body=make_checkpoint_bytes(),
        http_ok=True,
        fail_at_chunk=None,
        size_delta=100,
        expected_error=LancetHTTPError,
        expected_message="Incomplete download",
    ),
    "exact_size_non_zip": DownloadFailureScenario(
        body=b"x" * len(make_checkpoint_bytes()),
        http_ok=True,
        fail_at_chunk=None,
        size_delta=0,
        expected_error=LancetHTTPError,
        expected_message="not a valid checkpoint",
    ),
}


class TestDownloadFailures:
    """Test that failed downloads raise and leave no files behind."""

    @pytest.mark.parametrize("scenario", DOWNLOAD_FAILURE_SCENARIOS.values(), ids=DOWNLOAD_FAILURE_SCENARIOS.keys())
    def test_failure(
        self,
        scenario: DownloadFailureScenario,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: pathlib.Path,
    ) -> None:
        """Each failure scenario raises, and neither the model file nor a .part file remains."""
        model_path = install_cache_dir(monkeypatch, tmp_path)
        install_fake_get(
            monkeypatch,
            scenario.body,
            http_ok=scenario.http_ok,
            fail_at_chunk=scenario.fail_at_chunk,
            size_delta=scenario.size_delta,
        )

        with pytest.raises(scenario.expected_error) as exc_info:
            ComicTextDetectorCache().comic_text_detector_path()

        if scenario.expected_message:
            assert scenario.expected_message in str(exc_info.value)
        assert not model_path.exists()
        assert not model_path.with_suffix(".pt.part").exists()


class TestRequestFailures:
    """Test request-level failures before a response stream exists."""

    @pytest.mark.parametrize(
        "request_error",
        [
            requests.exceptions.ConnectionError("connection refused"),
            requests.exceptions.Timeout("request timed out"),
        ],
        ids=["connection_error", "timeout"],
    )
    def test_wraps_request_error(
        self,
        request_error: requests.RequestException,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: pathlib.Path,
    ) -> None:
        """Connection and timeout failures are normalized to LancetHTTPError without leaving files behind."""
        model_path = install_cache_dir(monkeypatch, tmp_path)
        monkeypatch.setattr(
            "lancet.text_detector_client.model_cache.requests.get",
            Mock(side_effect=request_error),
        )

        with pytest.raises(LancetHTTPError, match=FAILED_DOWNLOAD_RE):
            ComicTextDetectorCache().comic_text_detector_path()

        assert not model_path.exists()
        assert not model_path.with_suffix(".pt.part").exists()


class ContentLengthScenario(typing.NamedTuple):
    """A Content-Length header value and parsed result."""

    header: str | None
    expected: int


CONTENT_LENGTH_SCENARIOS: dict[str, ContentLengthScenario] = {
    "missing": ContentLengthScenario(None, 0),
    "malformed": ContentLengthScenario("unknown", 0),
    "valid": ContentLengthScenario("123", 123),
}


class TestContentLength:
    """Test tolerant Content-Length parsing."""

    @pytest.mark.parametrize("scenario", CONTENT_LENGTH_SCENARIOS.values(), ids=CONTENT_LENGTH_SCENARIOS.keys())
    def test_parse(self, scenario: ContentLengthScenario) -> None:
        """Missing and malformed headers return zero while integers are parsed."""
        response = FakeResponse(b"")
        if scenario.header is None:
            response.headers.pop("Content-Length")
        else:
            response.headers["Content-Length"] = scenario.header
        assert content_length(response) == scenario.expected


class HeaderlessDownloadScenario(typing.NamedTuple):
    """A download header, body, and expected full-cache outcome."""

    header: str | None
    body: bytes
    expect_error: bool


HEADERLESS_DOWNLOAD_SCENARIOS: dict[str, HeaderlessDownloadScenario] = {
    "missing_header_valid_checkpoint": HeaderlessDownloadScenario(None, make_checkpoint_bytes(), False),
    "missing_header_wrong_size": HeaderlessDownloadScenario(None, b"wrong checkpoint", True),
}


class TestHeaderlessDownload:
    """Test full cache validation when Content-Length is unavailable."""

    @pytest.mark.parametrize(
        "scenario", HEADERLESS_DOWNLOAD_SCENARIOS.values(), ids=HEADERLESS_DOWNLOAD_SCENARIOS.keys()
    )
    def test_download(
        self, scenario: HeaderlessDownloadScenario, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
    ) -> None:
        """Unusable headers skip HTTP comparison but never bypass pinned validation."""
        model_path = install_cache_dir(monkeypatch, tmp_path)
        install_fake_get(
            monkeypatch,
            scenario.body,
            include_content_length=scenario.header is not None,
            content_length_value=scenario.header,
        )
        if scenario.expect_error:
            with pytest.raises(LancetHTTPError, match=UNEXPECTED_CHECKPOINT_SIZE_RE):
                ComicTextDetectorCache().comic_text_detector_path()
            assert model_path.exists() is False
            assert model_path.with_suffix(".pt.part").exists() is False
            return
        assert ComicTextDetectorCache().comic_text_detector_path() == model_path
        assert model_path.read_bytes() == scenario.body


PINNED_SIZE_SCENARIOS: dict[str, bytes] = {
    "short_payload": b"wrong checkpoint",
    "single_byte_payload": b"x",
}


class TestPinnedCheckpointSize:
    """Test pinned-size validation independently of HTTP length."""

    @pytest.mark.parametrize("contents", PINNED_SIZE_SCENARIOS.values(), ids=PINNED_SIZE_SCENARIOS.keys())
    def test_rejects_wrong_asset_size(self, contents: bytes, tmp_path: pathlib.Path) -> None:
        """Matching HTTP length cannot override the pinned release size."""
        partial_path = tmp_path / "checkpoint.pt.part"
        partial_path.write_bytes(contents)
        with pytest.raises(LancetHTTPError, match=UNEXPECTED_CHECKPOINT_SIZE_RE):
            raise_if_incomplete(partial_path, len(contents))


REPLACE_FAILURE_SCENARIOS: dict[str, str] = {
    "replace_failed": "replace failed",
    "permission_denied": "permission denied",
}


class TestReplaceFailure:
    """Test cleanup when atomic cache replacement fails."""

    @pytest.mark.parametrize("error_message", REPLACE_FAILURE_SCENARIOS.values(), ids=REPLACE_FAILURE_SCENARIOS.keys())
    def test_partial_is_removed(
        self, error_message: str, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
    ) -> None:
        """A failed final replacement leaves neither a model nor partial file."""
        model_path = install_cache_dir(monkeypatch, tmp_path)
        install_fake_get(monkeypatch, make_checkpoint_bytes())
        error = OSError(error_message)
        monkeypatch.setattr("lancet.text_detector_client.model_cache.os.replace", Mock(side_effect=error))

        with pytest.raises(OSError) as exc_info:
            ComicTextDetectorCache().comic_text_detector_path()

        assert exc_info.value is error
        assert model_path.exists() is False
        assert model_path.with_suffix(".pt.part").exists() is False
