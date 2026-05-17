from __future__ import annotations

import uuid
from typing import Any

import boto3
from botocore.config import Config as BotocoreConfig

from app.config import settings


def _make_s3() -> Any:
    return boto3.client(
        "s3",
        endpoint_url=f"https://s3.{settings.scw_region}.scw.cloud",
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
    *,
    public: bool = False,
) -> str:
    """Upload bytes to Scaleway Object Storage.

    Returns the canonical storage URL used as the persistent reference.
    Pass public=True for files that must be openable by anyone with the link
    (invoices, budgets). Leave False for private files (voice notes, photos).
    """
    key = f"{contractor_id}/{entity_type}/{uuid.uuid4()}.{ext}"
    kwargs: dict[str, object] = {
        "Bucket": settings.scw_bucket,
        "Key": key,
        "Body": file_bytes,
    }
    if public:
        kwargs["ACL"] = "public-read"
    _make_s3().put_object(**kwargs)
    return f"https://{settings.scw_bucket}.s3.{settings.scw_region}.scw.cloud/{key}"


def presign_url(storage_url: str, expires_seconds: int = 3600) -> str:
    """Return a time-limited GET URL for a storage object.

    Accepts the canonical URL returned by upload_file.
    """
    prefix = f"https://{settings.scw_bucket}.s3.{settings.scw_region}.scw.cloud/"
    key = storage_url.removeprefix(prefix)
    return _make_s3().generate_presigned_url(  # type: ignore[no-any-return]
        "get_object",
        Params={"Bucket": settings.scw_bucket, "Key": key},
        ExpiresIn=expires_seconds,
    )
