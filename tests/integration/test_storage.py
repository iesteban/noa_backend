"""Integration tests for the S3 storage client against MinIO (local dev).

These tests require MinIO to be running (`docker compose up -d minio minio_init`)
and S3_ENDPOINT_URL to be set to http://localhost:9000. They are skipped
automatically when MinIO is not reachable.
"""
from __future__ import annotations

import urllib.error
import urllib.request
import uuid

import pytest

from app.config import settings
from app.storage.client import delete_file, presign_url, upload_file


def _minio_reachable() -> bool:
    if not settings.s3_endpoint_url:
        return False
    try:
        urllib.request.urlopen(
            f"{settings.s3_endpoint_url}/minio/health/live", timeout=2
        )
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _minio_reachable(),
    reason="MinIO not reachable — run `docker compose up -d minio minio_init`",
)

_CONTRACTOR_ID = str(uuid.uuid4())
_CONTENT = b"hello from integration test"


def test_upload_returns_expected_url() -> None:
    url = upload_file(_CONTRACTOR_ID, "invoices", _CONTENT, "pdf")

    assert url.startswith(settings.s3_endpoint_url)
    assert settings.scw_bucket in url
    assert url.endswith(".pdf")

    delete_file(url)


def test_presign_url_is_downloadable() -> None:
    url = upload_file(_CONTRACTOR_ID, "invoices", _CONTENT, "pdf")
    try:
        signed = presign_url(url, expires_seconds=60)
        with urllib.request.urlopen(signed, timeout=5) as resp:
            assert resp.status == 200
            assert resp.read() == _CONTENT
    finally:
        delete_file(url)


def test_delete_removes_object() -> None:
    url = upload_file(_CONTRACTOR_ID, "invoices", _CONTENT, "pdf")
    delete_file(url)

    signed = presign_url(url, expires_seconds=60)
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(signed, timeout=5)
    assert exc_info.value.code in (403, 404)  # 404 on MinIO, 403 on Scaleway for deleted objects


def test_upload_preserves_content_across_entity_types() -> None:
    urls = []
    payloads = {
        "invoices": b"%PDF invoice content",
        "budgets": b"%PDF budget content",
        "voice": b"ogg audio bytes",
    }
    try:
        for entity_type, content in payloads.items():
            ext = "pdf" if entity_type != "voice" else "ogg"
            url = upload_file(_CONTRACTOR_ID, entity_type, content, ext)
            urls.append((url, content))

        for url, expected in urls:
            signed = presign_url(url, expires_seconds=60)
            with urllib.request.urlopen(signed, timeout=5) as resp:
                assert resp.read() == expected
    finally:
        for url, _ in urls:
            delete_file(url)
