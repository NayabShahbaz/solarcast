"""[Member 1] Object-storage helpers that work with DagsHub OR AWS S3, unchanged.

Which backend is used depends only on .env:
- DagsHub (now):  S3_ENDPOINT_URL=https://dagshub.com/api/v1/repo-buckets/s3/<user>
                  AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY = your DagsHub token
- AWS (later):    S3_ENDPOINT_URL empty, credentials from AWS_PROFILE or the EC2 instance role

See planning/aws_migration.md for the switch.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

import boto3

from solarcast.config import env

log = logging.getLogger(__name__)


@lru_cache
def client():
    """boto3 S3 client. Credentials come from the standard AWS env vars / profile / role."""
    session = boto3.session.Session(profile_name=env("AWS_PROFILE") or None)
    return session.client(
        "s3",
        endpoint_url=env("S3_ENDPOINT_URL") or None,  # None -> real AWS S3
        region_name=env("AWS_REGION") or "us-east-1",
    )


def bucket() -> str:
    name = env("S3_BUCKET")
    if not name:
        raise RuntimeError("S3_BUCKET is not set - copy .env.example to .env and fill it in")
    return name


def key(prefix_var: str, name: str) -> str:
    """Build a key from a prefix env var, e.g. key("S3_RAW_PREFIX", "pvgis/2024.csv")."""
    return f"{env(prefix_var, '')}{name}"


def upload(local_path: Path, object_key: str) -> str:
    client().upload_file(str(local_path), bucket(), object_key)
    return f"s3://{bucket()}/{object_key}"


def download(object_key: str, local_path: Path) -> Path:
    local_path = Path(local_path)
    local_path.parent.mkdir(parents=True, exist_ok=True)
    client().download_file(bucket(), object_key, str(local_path))
    return local_path


def is_configured() -> bool:
    """True once .env has a real bucket (not missing and not a <placeholder>)."""
    name = env("S3_BUCKET") or ""
    endpoint = env("S3_ENDPOINT_URL") or ""
    return bool(name) and "<" not in name and "<" not in endpoint


def maybe_upload(local_path: Path, object_key: str) -> str | None:
    """Upload if storage is configured; otherwise log and continue (local-only mode)."""
    if not is_configured():
        log.info("storage not configured - kept %s local only", local_path)
        return None
    return upload(local_path, object_key)


def list_keys(prefix: str = "") -> list[str]:
    paginator = client().get_paginator("list_objects_v2")
    return [
        obj["Key"]
        for page in paginator.paginate(Bucket=bucket(), Prefix=prefix)
        for obj in page.get("Contents", [])
    ]
