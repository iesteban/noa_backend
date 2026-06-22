from __future__ import annotations

import uuid
from typing import Any

import boto3
from botocore.config import Config as BotocoreConfig

from app.config import settings


def _endpoint_url() -> str:
    return settings.s3_endpoint_url or f"https://s3.{settings.scw_region}.scw.cloud"


def _base_url() -> str:
    if settings.s3_endpoint_url:
        return f"{settings.s3_endpoint_url}/{settings.scw_bucket}"
    return f"https://{settings.scw_bucket}.s3.{settings.scw_region}.scw.cloud"


def _make_s3() -> Any:
    return boto3.client(
        "s3",
        endpoint_url=_endpoint_url(),
        aws_access_key_id=settings.scw_access_key,
        aws_secret_access_key=settings.scw_secret_key,
        config=BotocoreConfig(signature_version="s3v4"),
        region_name=settings.scw_region,
    )


def upload_file(
    contractor_id: str | uuid.UUID,
    entity_type: str,
    file_bytes: bytes,
    ext: str,
) -> str:
    """Upload bytes to object storage.

    Returns the canonical storage URL used as the persistent reference. The
    bucket is private, so callers hand out access via presign_url() at send
    time rather than relying on public object ACLs.
    """
    key = f"{contractor_id}/{entity_type}/{uuid.uuid4()}.{ext}"
    _make_s3().put_object(Bucket=settings.scw_bucket, Key=key, Body=file_bytes)
    return f"{_base_url()}/{key}"


def delete_file(storage_url: str) -> None:
    """Delete an object from storage given its canonical URL."""
    key = storage_url.removeprefix(f"{_base_url()}/")
    _make_s3().delete_object(Bucket=settings.scw_bucket, Key=key)


def presign_url(storage_url: str, expires_seconds: int = 3600) -> str:
    """Return a time-limited GET URL for a storage object.

    Accepts the canonical URL returned by upload_file.
    """
    key = storage_url.removeprefix(f"{_base_url()}/")
    return _make_s3().generate_presigned_url(  # type: ignore[no-any-return]
        "get_object",
        Params={"Bucket": settings.scw_bucket, "Key": key},
        ExpiresIn=expires_seconds,
    )
