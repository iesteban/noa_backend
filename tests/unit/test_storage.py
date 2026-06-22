"""Unit tests for app/storage/client.py — boto3 is mocked throughout."""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from app.config import settings
from app.storage.client import _base_url, presign_url, upload_file


@pytest.fixture
def s3(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    mock = MagicMock()
    monkeypatch.setattr("app.storage.client._make_s3", lambda: mock)
    return mock


# ---------------------------------------------------------------------------
# upload_file
# ---------------------------------------------------------------------------

class TestUploadFile:
    def test_returns_url_with_base(self, s3: MagicMock) -> None:
        url = upload_file("abc-123", "voice", b"audio", "ogg")
        assert url.startswith(_base_url())

    def test_url_contains_contractor_id(self, s3: MagicMock) -> None:
        url = upload_file("abc-123", "voice", b"audio", "ogg")
        assert "abc-123" in url

    def test_url_contains_entity_type(self, s3: MagicMock) -> None:
        url = upload_file("abc-123", "invoices", b"pdf", "pdf")
        assert "invoices" in url

    def test_url_ends_with_extension(self, s3: MagicMock) -> None:
        url = upload_file("abc-123", "voice", b"audio", "ogg")
        assert url.endswith(".ogg")

    def test_url_contains_bucket(self, s3: MagicMock) -> None:
        url = upload_file("abc-123", "voice", b"audio", "ogg")
        assert settings.scw_bucket in url

    def test_each_upload_has_unique_path(self, s3: MagicMock) -> None:
        url1 = upload_file("abc-123", "voice", b"audio", "ogg")
        url2 = upload_file("abc-123", "voice", b"audio", "ogg")
        assert url1 != url2

    def test_uuid_contractor_id_stringified(self, s3: MagicMock) -> None:
        cid = uuid.uuid4()
        url = upload_file(cid, "photos", b"img", "jpg")
        assert str(cid) in url

    def test_calls_put_object_once(self, s3: MagicMock) -> None:
        upload_file("abc-123", "voice", b"audio", "ogg")
        s3.put_object.assert_called_once()

    def test_put_object_receives_correct_body(self, s3: MagicMock) -> None:
        upload_file("abc-123", "voice", b"my-audio", "ogg")
        assert s3.put_object.call_args.kwargs["Body"] == b"my-audio"

    def test_put_object_receives_correct_bucket(self, s3: MagicMock) -> None:
        upload_file("abc-123", "voice", b"audio", "ogg")
        assert s3.put_object.call_args.kwargs["Bucket"] == settings.scw_bucket

    def test_put_object_key_matches_url_path(self, s3: MagicMock) -> None:
        url = upload_file("abc-123", "voice", b"audio", "ogg")
        key = s3.put_object.call_args.kwargs["Key"]
        assert url.endswith(key)

    def test_upload_never_sets_acl(self, s3: MagicMock) -> None:
        # The bucket is private; access is granted via presign_url, not ACLs.
        upload_file("abc-123", "invoices", b"pdf", "pdf")
        assert "ACL" not in s3.put_object.call_args.kwargs


# ---------------------------------------------------------------------------
# presign_url
# ---------------------------------------------------------------------------

class TestPresignUrl:
    def _storage_url(self, key: str = "abc/voice/x.ogg") -> str:
        return f"{_base_url()}/{key}"

    def test_returns_value_from_boto3(self, s3: MagicMock) -> None:
        s3.generate_presigned_url.return_value = "https://signed.example.com/file"
        result = presign_url(self._storage_url())
        assert result == "https://signed.example.com/file"

    def test_calls_get_object_operation(self, s3: MagicMock) -> None:
        s3.generate_presigned_url.return_value = "https://..."
        presign_url(self._storage_url())
        assert s3.generate_presigned_url.call_args.args[0] == "get_object"

    def test_passes_correct_key(self, s3: MagicMock) -> None:
        s3.generate_presigned_url.return_value = "https://..."
        presign_url(self._storage_url("contractor-id/invoices/file.pdf"))
        params = s3.generate_presigned_url.call_args.kwargs["Params"]
        assert params["Key"] == "contractor-id/invoices/file.pdf"

    def test_passes_correct_bucket(self, s3: MagicMock) -> None:
        s3.generate_presigned_url.return_value = "https://..."
        presign_url(self._storage_url())
        params = s3.generate_presigned_url.call_args.kwargs["Params"]
        assert params["Bucket"] == settings.scw_bucket

    def test_default_expiry_is_3600(self, s3: MagicMock) -> None:
        s3.generate_presigned_url.return_value = "https://..."
        presign_url(self._storage_url())
        assert s3.generate_presigned_url.call_args.kwargs["ExpiresIn"] == 3600

    def test_custom_expiry_passed_through(self, s3: MagicMock) -> None:
        s3.generate_presigned_url.return_value = "https://..."
        presign_url(self._storage_url(), expires_seconds=7200)
        assert s3.generate_presigned_url.call_args.kwargs["ExpiresIn"] == 7200

    def test_roundtrip_key_from_upload_url(self, s3: MagicMock) -> None:
        """Key extracted from upload_file's URL matches key sent to put_object."""
        s3.generate_presigned_url.return_value = "https://..."
        storage_url = upload_file("ctr-1", "photos", b"img", "jpg")
        uploaded_key = s3.put_object.call_args.kwargs["Key"]

        presign_url(storage_url)
        presigned_key = s3.generate_presigned_url.call_args.kwargs["Params"]["Key"]
        assert presigned_key == uploaded_key
